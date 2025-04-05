#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
Interfaces to Radiacode File Formats: tracks, spectra, spectrograms, and N42 conversion

Conventions:

durations, integration times, etc. are timedeltas. They get converted to/from seconds only
at file io time.

Timestamps are stored as datetimes. Unix epoch seconds can't express time before 1970, so
you can't directly ask for gettimeofday() when the trinity test happened, but the datetime
object itself can store time back to year 1. Radiacode, python, linux, and modern PCs were
created after the unix epoch; so the epoch seconds are not a major limitation
"""

import importlib
from binascii import hexlify, unhexlify
from datetime import datetime, timedelta
from hashlib import sha256
from re import sub as re_sub
from struct import pack as struct_pack
from struct import unpack as struct_unpack
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import xmltodict

from .rc_types import (
    DATEFMT_T,
    DATEFMT_TZ,
    DATEFMT_Z,
    DataclassEncoderMixin,
    EnergyCalibration,
    Number,
    SpectrogramPoint,
    SpectrumLayer,
    TrackPoint,
    _outtatime,
)
from .rc_utils import (
    UTC,
    DateTime2FileTime,
    FileTime2DateTime,
    format_datetime,
    parse_datetime,
)

TimeStampish = Union[Number, datetime]
TimeDurationish = Union[Number, timedelta]


_RCTRK_DEFAULT_NO_SERIAL_NUMBER: str = "Unknown Device"  # Radiacode app accepts this
_RCTRK_DEFAULT_FLAGS: str = "EC"  # Not sure what this does


class RcTrack:
    "Radiacode Track (.rctrk) interface"

    def __init__(self, filename: Optional[str] = None) -> None:
        self._clear_data()
        self._columns = ["DateTime", "Latitude", "Longitude", "Accuracy", "DoseRate", "CountRate", "Comment"]
        self.filename = filename

        self._clear_data()
        if filename:
            self.load_file(filename)

    def _clear_data(self) -> None:
        "Clear out the header, in preparation for loading"
        self.timestamp: datetime = datetime.now(UTC)
        self.name: str = ""
        self.serialnumber: str = _RCTRK_DEFAULT_NO_SERIAL_NUMBER
        self.comment: str = ""
        self.flags: str = _RCTRK_DEFAULT_FLAGS
        self.points: List[TrackPoint] = []

    def as_dict(self) -> Dict[str, Any]:
        "Convert the internal state into a format that could be easily jsonified"
        rv = {
            "name": self.name,
            "serialnumber": self.serialnumber,
            "comment": self.comment,
            "flags": self.flags,
            "points": [self._format_trackpoint(x) for x in self.points],
        }
        return rv

    def from_dict(self, d: Dict[str, Any]) -> bool:
        """
        Populate the in-memory representation from a dict:

        {
            "name": str,
            "serialnumber": str,
            "comment": str,
            "flags": str,
            "points": [
                {
                    "dt": datetime(),
                    "latitude": float(),
                    "longitude": float(),
                    "accuracy": float(),
                    "doserate": float(),
                    "countrate": float(),
                    "comment": str(),
                },
                ...
            ]
        }
        """

        if sorted(d.keys()) != ["comment", "flags", "name", "points", "serialnumber"]:
            raise ValueError

        self._clear_data()
        self.name = d["name"]
        self.serialnumber = d["serialnumber"]
        self.comment = d["comment"]
        self.flags = d["flags"]

        self.points = [
            TrackPoint(
                dt=p["dt"],
                latitude=p["latitude"],
                longitude=p["longitude"],
                accuracy=p["accuracy"],
                doserate=p["doserate"],
                countrate=p["countrate"],
                comment=p["comment"],
            )
            for p in d["points"]
        ]
        return True

    def _format_trackpoint(self, tp: TrackPoint) -> Dict[str, Any]:
        "render a trackpoint as a simple dict"
        # fz = [None] + list(tp._asdict().values())
        rv = {"filetime": -1}
        rv.update(tp.__dict__)
        rv["filetime"] = DateTime2FileTime(rv["dt"])
        # rv["datetime"] = format_datetime(rv["dt"], DATEFMT_TZ)
        return rv

    def write_file(self, filename: str) -> None:
        "Write the in-memory representation to filesystem"
        if not self.name:
            self.name = f"Track {self.timestamp.replace(tzinfo=None,microsecond=0)}"
        with open(filename, "wt") as ofd:
            print("Track: " + "\t".join([self.name, self.serialnumber, self.comment, self.flags]), file=ofd)
            # Patch column names in output file.
            print("\t".join(["Timestamp", "Time"] + self._columns[1:]), file=ofd)
            line = "{filetime}\t{dt}\t{latitude}\t{longitude}\t{accuracy}\t{doserate}\t{countrate}\t{comment}"
            for p in self.points:
                print(line.format_map(self._format_trackpoint(p)), file=ofd)

    def load_file(self, filename: str) -> None:
        "Load a track from the filesystem"
        with open(filename, "rt") as ifd:
            self._clear_data()
            nf = len(self._columns)
            for n, line in enumerate(ifd):
                if n == 0:
                    if not line.startswith("Track:"):
                        raise ValueError("This doesn't look like a valid track - missing header")
                    self.name, self.serialnumber, self.comment, self.flags = line.split("\t")
                    self.name = self.name.split(": ", 1)[1]
                    self.flags = self.flags.strip()
                    continue
                if n == 1:
                    if not line.startswith("Timestamp"):
                        raise ValueError("This doesn't look like a valid track - missing column signature")
                    continue
                fields: List[Any] = line.split("\t")
                if len(fields) != nf + 1:
                    raise ValueError(f"Incorrect number of values on line {n+1}")
                fields[1] = FileTime2DateTime(fields[0]).replace(
                    tzinfo=UTC
                )  # filetime is higher resolution than YYYY-mm-dd HH:MM:SS
                for i in range(2, 7):
                    fields[i] = float(fields[i])
                fields[-1] = fields[-1].rstrip("\n")
                self.points.append(
                    TrackPoint(
                        dt=fields[1],
                        latitude=fields[2],
                        longitude=fields[3],
                        accuracy=fields[4],
                        doserate=fields[5],
                        countrate=fields[6],
                        comment=fields[7],
                    )
                )

    def add_point_dict(self, d) -> None:
        """
        Add a track point from a dict with the following keys

        ["DateTime", "Latitude", "Longitude", "Accuracy", "DoseRate", "CountRate", "Comment"]

        Spelling counts - that's the way they are in the .rcspg header
        """
        self.add_point(
            dt=d["DateTime"],
            latitude=d["Latitude"],
            longitude=d["Longitude"],
            accuracy=d["Accuracy"],
            dose_rate=d["DoseRate"],
            count_rate=d["CountRate"],
            comment=d.get("Comment", ""),
        )

    def add_point(
        self,
        dt: datetime,
        latitude: float,
        longitude: float,
        accuracy: float,
        dose_rate: float,
        count_rate: float,
        comment: str = "",
    ) -> None:
        "Wrapper around TrackPoint, but accepts a DateTime which is more useful"
        self.points.append(
            TrackPoint(
                dt=dt,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy,
                doserate=dose_rate,
                countrate=count_rate,
                comment=comment,
            )
        )
        if len(self.points) < 2:
            if dt.tzinfo is None:
                raise TypeError("offset-aware datetime required")  # similar to the comparison below
            self.timestamp = dt
        else:
            self.timestamp = min(self.timestamp, dt)


class RcSpectrum:
    "Radiacode Spectrum (.xml)"

    def __init__(self, filename: str = "") -> None:
        self.fg_spectrum: Optional[SpectrumLayer] = None
        self.bg_spectrum: Optional[SpectrumLayer] = None
        self.note: str = ""

        if filename:
            self.load_file(filename)

    def __repr__(self) -> str:
        return "Spectrum(" f"\n\tfg={self.fg_spectrum}" f"\n\tbg={self.bg_spectrum}" f'\n\tnote="{self.note}"\n)'

    def _parse_spectrum(self, spectrum: Dict[str, Any]) -> SpectrumLayer:
        """Given an spectrum dict, return useful items"""
        cal = [float(f) for f in spectrum["EnergyCalibration"]["Coefficients"]["Coefficient"]]
        polynomial_order = int(spectrum["EnergyCalibration"]["PolynomialOrder"])

        channels = int(spectrum["NumberOfChannels"])
        counts = [int(i) for i in spectrum["Spectrum"]["DataPoint"]]
        if len(counts) != channels:
            raise ValueError("spectrum length != number of channels")

        if 2 != polynomial_order:
            raise ValueError("invalid calibration order")

        if len(cal) != polynomial_order + 1:
            raise ValueError("Inconsistent calibration polynomial")

        rv = SpectrumLayer(
            spectrum_name=spectrum["SpectrumName"],
            device_model="",
            serial_number=spectrum.get("SerialNumber", None),
            calibration=EnergyCalibration(a0=cal[0], a1=cal[1], a2=cal[2]),
            duration=timedelta(seconds=int(spectrum["MeasurementTime"])),
            channels=channels,
            counts=counts,
            comment=spectrum.get("Comment", ""),
            timestamp=None,
        )

        return rv

    def load_file(self, filename: str):
        "Load a spectrum from disk"
        with open(filename) as ifd:
            self.load_str(ifd.read())
        return self

    def load_str(self, data: str) -> None:
        "Load a spectrum from a string, such as one might get over the network or have in memory"
        sp = xmltodict.parse(data, dict_constructor=dict)["ResultDataFile"]["ResultDataList"]["ResultData"]

        tmp = sp["EnergySpectrum"]  # explode if the spectrum is missing. No foreground = not useful
        self.fg_spectrum = self._parse_spectrum(tmp)
        self.fg_spectrum.device_model = sp["DeviceConfigReference"]["Name"]

        try:
            background_spectrum = sp.get("BackgroundEnergySpectrum")
            self.bg_spectrum = self._parse_spectrum(background_spectrum)
        except (KeyError, AttributeError, TypeError):
            background_spectrum = None

        # older versions of data files don't have start and end times
        if background_spectrum:
            try:
                start_times = [parse_datetime(s, DATEFMT_T) for s in sp.get("StartTime", None)]
                end_times = [parse_datetime(s, DATEFMT_T) for s in sp.get("EndTime", None)]
                self.fg_spectrum.timestamp = start_times[0]
                self.fg_spectrum.duration = end_times[0] - start_times[0]
                if isinstance(self.bg_spectrum, SpectrumLayer):
                    self.bg_spectrum.timestamp = start_times[1]
                    self.bg_spectrum.duration = end_times[1] - start_times[1]

            except (KeyError, TypeError, AttributeError):
                pass
        else:  # no background spectrum in this file
            try:
                a = parse_datetime(sp.get("StartTime", None), DATEFMT_T)
                b = parse_datetime(sp.get("EndTime", None), DATEFMT_T)
                d = b - a
                self.fg_spectrum.timestamp = a
                self.fg_spectrum.duration = d
            except (KeyError, TypeError, AttributeError):
                pass

    def _spec_layer_to_elements(self, bg=False) -> List[str]:
        sl: SpectrumLayer = self.bg_spectrum if bg is True else self.fg_spectrum
        sc = sl.comment if sl.comment else ""
        st = sl.timestamp
        et = sl.timestamp + sl.duration

        b = "Background" if bg else ""
        rv = [
            f"<StartTime>{st.strftime(DATEFMT_T)}</StartTime>",
            f"<EndTime>{et.strftime(DATEFMT_T)}</EndTime>\n",
            f"<{b}EnergySpectrum>",
            f"<NumberOfChannels>{sl.channels}</NumberOfChannels>",
            "<ChannelPitch>1</ChannelPitch>",
            f"<SpectrumName><![CDATA[{sl.spectrum_name}]]></SpectrumName>",
            f"<Comment>{sc}</Comment>",
            f"<SerialNumber>{sl.serial_number}</SerialNumber>",
            #
            "<EnergyCalibration>",
            "<PolynomialOrder>2</PolynomialOrder>",
            "<Coefficients>",
            *[f"\t<Coefficient>{k}</Coefficient>" for k in sl.calibration.__dict__.values()],
            "</Coefficients>",
            "</EnergyCalibration>",
            #
            f"<MeasurementTime>{int(sl.duration.total_seconds())}</MeasurementTime>",
            "<Spectrum>",
            *[f"\t<DataPoint>{k}</DataPoint>" for k in sl.counts],
            "</Spectrum>",
            f"<{b}/EnergySpectrum>",
        ]
        return rv

    def write_file(self, filename: str) -> None:
        leader = [
            '<?xml version="1.0"?>',
            '<ResultDataFile xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
            "<FormatVersion>120920</FormatVersion>",
            "<ResultDataList>",
            "<ResultData>",
        ]

        bgname = self.bg_spectrum.spectrum_name if isinstance(self.bg_spectrum, SpectrumLayer) else ""
        devconfig = [
            "<DeviceConfigReference>",
            f"<Name>{self.fg_spectrum.device_model}</Name>",
            "</DeviceConfigReference>",
            "<SampleInfo>",
            f"<Name><![CDATA[{self.fg_spectrum.spectrum_name}]]></Name>",
            "<Note><![CDATA[]]></Note>",
            "</SampleInfo>",
            f"<BackgroundSpectrumFile>{bgname}</BackgroundSpectrumFile>",
        ]

        trailer = [
            "<Visible>true</Visible>",
            "<PulseCollection>",
            "<Format>Base64 encoded binary</Format>",
            "<Pulses />",
            "</PulseCollection>",
            "</ResultData>",
            "</ResultDataList>",
            "</ResultDataFile>",
        ]
        print("\n".join(leader))
        print("\n".join(devconfig))
        print("\n".join(self._spec_layer_to_elements()))
        if self.bg_spectrum and isinstance(self.bg_spectrum, SpectrumLayer):
            print("\n".join(self._spec_layer_to_elements(bg=True)))
        print("\n".join(trailer))

    def as_dict(self) -> Dict[str, Any]:
        """
        Convert an RcSpectrum into a dict that could be safely jsonified with RcJSONEncoder
        That looks like:
        {
            "fg": { ... },    #  SpectrumLayer._asdict()
            "bg": { ... },    #  SpectrumLayer._asdict()
            "note": ""        #  descriptive note
        }

        See `make_layer_from_dict` for more details
        """
        rv: Dict[str, Any] = {
            "fg": None,
            "bg": None,
            "note": self.note,
        }
        if self.fg_spectrum:
            rv["fg"] = self.fg_spectrum.__dict__
        if self.bg_spectrum:
            rv["bg"] = self.bg_spectrum.__dict__

        return rv

    def make_layer_from_dict(self, d: Dict[str, Any]) -> SpectrumLayer:
        """
        Convert a dict into a SpectrumLayer which can then be used in an RcSpectrum.
        The dict must look like this

        {
            "spectrum_name": "",         # str
            "device_model: "",           # str
            "serial_number: "",          # str
            "calibration: [a0, a1, a2],  # list|tuple, float*3
            "timestamp": t,              # datetime
            "duration": d,               # timedelta
            "channels: n,                # int
            "counts: [int, ... , int],   # list|tuple, length must equal the number of channels
            "comment: "",                # str, optional
        }
        """

        if len(d["counts"]) != d["channels"]:
            raise ValueError("Inconsistent channel count in layer dict")
        rv = SpectrumLayer(
            spectrum_name=d["spectrum_name"],
            device_model=d["device_model"],
            serial_number=d["serial_number"],
            calibration=d["calibration"],
            timestamp=d["timestamp"],
            duration=d["duration"],
            channels=int(d["channels"]),
            counts=[int(i) for i in d["counts"]],
            comment=d.get("comment", ""),
        )

        return rv

    def from_dict(self, d: Dict[str, Any]):
        """
        The inverse of `as_dict`. Use this to load a jsonified RcSpectrum
        """
        self.note = d.get("note", "")
        self.fg_spectrum = self.make_layer_from_dict(d["fg"])

        bg = self.make_layer_from_dict(d["bg"])
        if bg:
            self.bg_spectrum = bg
        return self

    def uuid(self) -> str:
        "generate a uuid-shaped string based on the content of the spectrum file"
        h = sha256(str(self).encode()).hexdigest()[:32]
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

    def count_rate(self, bg: bool = False) -> float:
        if bg and not isinstance(self.bg_spectrum, SpectrumLayer):
            raise ValueError("bg_spectrum is undefined")
        n = sum(self.bg_spectrum.counts if bg else self.fg_spectrum.counts)
        t = self.bg_spectrum.duration if bg else self.fg_spectrum.duration
        return n / t.total_seconds()


class RcSpectrogram(DataclassEncoderMixin):
    """
    Radiacode Spectrogram (.rcspg)

    A Radiacode spectrogrum file has basically 3 parts.

    1. A metadata line with information like the device serial number, accumulatiion time,
       channel count, name, comment, ...
    2. The energy calibration, and the total intrated spectrum at the time recording started
    3. A series of timestamped channel counts: (timestamp, [counts]), (timestamp, [counts]), ...
       The counts are deltas since the last spectrum.

    The two expected use cases are loading a spectrogram from disk to plot it, and building
    a spectrogram from samples for writing to disk. This class works well enough to roundtrip
    the data and produce valid plots

    """

    def __init__(self, filename: str = "") -> None:
        self.name: str = ""
        self.timestamp: datetime = datetime.now()
        self.accumulation_time: timedelta = timedelta(0)
        self.channels: int = 0
        self.serial_number: str = ""
        self.flags: int = 1
        self.comment: str = ""
        self.calibration: EnergyCalibration = EnergyCalibration()
        # abusing this type a little bit, but it's not that wrong.
        # Some kind of timing indicaton, and a list of counts. In this case
        # that's total integration time for the historical spectrum.
        self.historical_spectrum: SpectrogramPoint = SpectrogramPoint()
        # saving spectra so that differences can be computed
        self.previous_spectrum: Optional[SpectrogramPoint] = None
        # and this is what it's really for: counts at a particular time.
        self.samples: List[SpectrogramPoint] = []
        if filename:
            self.load_file(filename)

    def __repr__(self) -> str:
        s = " " + self.comment if self.comment else ""
        return (
            f"Spectrogram(\n\tname='{self.name}',"
            f"\n\ttime='{self.timestamp}',"
            f"\n\tserial_number={self.serial_number},"
            f"\n\t{self.calibration},"
            f"\n\taccumulation={self.accumulation_time},"
            f"\n\tchannels={self.channels},"
            f"\n\tcomment:'{s}'"
            f"\n\tnum_samples={len(self.samples)})"
        )

    def _parse_header_line(self, line: str) -> None:
        if not line.startswith("Spectrogram:"):
            raise ValueError
        fields = [x.split(": ") for x in line.strip("\n").split("\t")]
        fields = dict(fields)
        self.name = fields["Spectrogram"]
        self.timestamp = FileTime2DateTime(int(fields["Timestamp"]))
        self.accumulation_time = timedelta(seconds=int(fields["Accumulation time"]))
        self.channels = int(fields["Channels"])
        self.serial_number = fields["Device serial"]
        self.flags = fields["Flags"]
        self.comment = fields["Comment"]

    def _make_header_line(self) -> str:
        """
        Create the first (header) line of the spectrum file

        Not all flag values are known, but bit 0 being unset means that the
        spectrogram recording was interrupted and resumed.
        """

        timestamp = DateTime2FileTime(self.timestamp)
        tstr = format_datetime(self.timestamp)

        self.name = self.name.strip()
        if not self.name:
            # and this version of time just looks like an int... for deduplication
            self.name = f"rcmulti_{self.timestamp.strftime('%Y%m%d%H%M%S')}_{self.serial_number}"

        fields = [
            f"Spectrogram: {self.name}",
            f"Time: {tstr}",
            f"Timestamp: {timestamp}",
            f"Accumulation time: {int(round(self.accumulation_time.total_seconds()))}",
            f"Channels: {self.channels}",
            f"Device serial: {self.serial_number.strip()}",
            f"Flags: {self.flags}",
            f"Comment: {self.comment}",
        ]
        return "\t".join(fields)

    def _parse_historical_spectrum_line(self, line: str) -> None:
        if not line.startswith("Spectrum:"):
            raise ValueError
        raw_data = line.replace("Spectrum:", "").replace(" ", "").strip()
        raw_data = unhexlify(raw_data)
        fmt = f"<I3f{len(raw_data)//4-4}I"
        tmp = struct_unpack(fmt, raw_data)
        self.calibration = EnergyCalibration(a0=tmp[1], a1=tmp[2], a2=tmp[3])
        self.historical_spectrum = SpectrogramPoint(td=timedelta(seconds=tmp[0]), counts=tmp[4:])

    def _make_historical_spectrum_line(self) -> str:
        """
        The second line of the spectrogram is the spectrum of the accumulated exposure
        since last data reset.
        (duration:int, coeffs:float[3], counts:int[1024])
        """
        v = struct_pack(
            f"<Ifff{len(self.historical_spectrum.counts)}I",
            int(self.historical_spectrum.td.total_seconds()),
            *self.calibration.values(),
            *self.historical_spectrum.counts,
        )
        v = hexlify(v, sep=" ").decode().upper()
        return f"Spectrum: {v}"

    def load_file(self, filename: str) -> None:
        with open(filename, "rt") as ifd:
            for n, line in enumerate(ifd):
                if n == 0:
                    self._parse_header_line(line)
                    continue
                elif n == 1:
                    self._parse_historical_spectrum_line(line)
                    continue
                else:
                    counts = [int(x) for x in line.strip().split()]
                    dt = FileTime2DateTime(counts.pop(0))
                    td = timedelta(seconds=counts.pop(0))
                    self.samples.append(SpectrogramPoint(dt=dt, td=td, counts=counts))

    def _make_spectrogram_line(self, l: SpectrogramPoint) -> str:
        """
        Format a SpectrogramPoint as line for the rcspg
        """
        rv = [DateTime2FileTime(l.dt), int(l.td.total_seconds())]
        rv.extend(l.counts)
        rv = "\t".join([str(x) for x in rv])
        rv = re_sub(r"(\s0)+$", "", rv)
        return rv

    def add_calibration(self, calibration: EnergyCalibration) -> None:
        self.calibration = calibration

    def add_point(
        self, counts: List[int], timestamp: Optional[TimeStampish] = None, duration: Optional[TimeDurationish] = None
    ) -> bool:
        """
        Add a datapoint to the spectrogram.

        Counts should be raw measurements from the device. This function takes
        care of computing the difference. Returns True if a point was added to
        history, False otherwise. If not given, timestamp is set to the system
        time.

        The first time this function is called, it will set the historical spectrum.
        """

        set_historical = False
        if self.channels == 0:
            self.channels = len(counts)
            set_historical = True
        elif len(counts) != self.channels:
            raise ValueError(f"Unexpected channel count != {self.channels}")

        # gin up a valid timestamp
        if isinstance(timestamp, datetime):
            pass
        elif isinstance(timestamp, int) or isinstance(timestamp, float):
            timestamp = datetime.fromtimestamp(timestamp)
        else:
            timestamp = datetime.now()

        if isinstance(duration, timedelta):
            pass
        elif isinstance(duration, int) or isinstance(duration, float):
            duration = timedelta(seconds=duration)
        else:
            duration = None

        if set_historical:
            self.historical_spectrum = SpectrogramPoint(dt=timestamp, counts=counts, td=duration)

        if self.previous_spectrum is None:
            self.previous_spectrum = SpectrogramPoint(dt=timestamp, counts=[0] * self.channels)
            return False

        dx = [z[0] - z[1] for z in zip(counts, self.previous_spectrum.counts)]
        self.samples.append(SpectrogramPoint(dt=timestamp, td=timestamp - self.previous_spectrum.dt, counts=dx))
        self.previous_spectrum = SpectrogramPoint(dt=timestamp, counts=counts)
        self.accumulation_time = self.samples[-1].dt - self.samples[0].dt
        return True

    def write_file(self, filename: str) -> None:
        "Dump the spectrogram to a file"
        if not self.accumulation_time:
            self.accumulation_time = self.samples[-1].dt - self.samples[0].dt
        with open(filename, "wt") as ofd:
            print(self._make_header_line(), file=ofd)
            print(self._make_historical_spectrum_line(), file=ofd)
            for s in self.samples:
                print(self._make_spectrogram_line(s), file=ofd)


class RcN42(DataclassEncoderMixin):
    "Minimal N42 implementation that can transcode to/from dual layer RadiaCode XML spectrum"

    def __init__(self, filename: str = "") -> None:
        self.serial_number: str = ""
        self.model: str = ""
        self.header: Dict[str, Any] = {}
        self.uuid: str = ""
        self.spectrum_data: RcSpectrum = RcSpectrum()
        self.rad_detector_information: Dict[str, Any] = {}
        self.rad_instrument_information: Dict[str, Any] = {}
        self._rdi: str = "radiacode-scinitillator-sipm"

        self._populate_header()
        if filename:
            self.load_file(filename)

    def _populate_header(self) -> None:
        self.header = {
            "@xmlns": "http://physics.nist.gov/N42/2011/N42",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "http://physics.nist.gov/N42/2011/N42 http://physics.nist.gov/N42/2011/n42.xsd",
            "@n42DocUUID": "",
            "RadInstrumentDataCreatorName": "https://github.com/ckuethe/radiacode-tools",
        }

    def _spectrum_layer_from_rad_measurement(self, rm: Dict[str, Any], ecz: Dict[str, Any]) -> SpectrumLayer:
        cal = [float(x) for x in ecz[rm["Spectrum"]["@energyCalibrationReference"]].split()]
        counts = [int(x) for x in rm["Spectrum"]["ChannelData"]["#text"].split()]

        return SpectrumLayer(
            spectrum_name=rm["Remark"].replace("Title: ", ""),
            device_model=self.model,
            serial_number=self.serial_number,
            calibration=EnergyCalibration(a0=cal[0], a1=cal[1], a2=cal[2]),
            timestamp=parse_datetime(rm["StartDateTime"], DATEFMT_T),
            duration=timedelta(seconds=float(rm["RealTimeDuration"].strip("PTS"))),
            channels=len(counts),
            counts=counts,
            comment="",
        )

    def _rad_measurement_from_spectrum_layer(self, sl: SpectrumLayer, fg: bool) -> Dict[str, Any]:
        tag = "fg"
        fb = "Fore"
        if fg is False:
            tag = "bg"
            fb = "Back"
        duration = f"PT{round(sl.duration.total_seconds())}S"
        if not sl.counts:
            raise ValueError(f"{tag} spectrum layer has no counts")
        if not isinstance(sl.timestamp, datetime) or sl.timestamp == _outtatime:
            raise ValueError(f"{tag} spectrum layer has no timestamp")

        return {
            "@id": f"radmeas-{tag}",
            # FIXME how to store the spectrum comment as well as the name?
            "Remark": sl.spectrum_name,
            "MeasurementClassCode": f"{fb}ground",
            "StartDateTime": sl.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "RealTimeDuration": duration,
            "Spectrum": {
                "@id": f"spectrum-{tag}",
                "@radDetectorInformationReference": self._rdi,
                "@energyCalibrationReference": f"ec-{tag}",
                "LiveTimeDuration": duration,
                "ChannelData": {
                    "@compressionCode": "None",
                    "#text": " ".join([f"{i}" for i in sl.counts]),
                },
            },
        }

    def _populate_rad_instrument_information(self, serial_number: str = "") -> bool:
        "Fill in the RadiationInstrumentInformation element, mostly for the scintillator type"
        if not self.serial_number and not serial_number:
            raise ValueError
        if serial_number:
            self.serial_number = serial_number
        self.model = f"RadiaCode-{self.serial_number.split('-')[1]}"

        radiacode_ver = importlib.metadata.version("radiacode")
        rctools_ver = importlib.metadata.version("radiacode-tools")
        self.rad_instrument_information = {
            "@id": "radiacode-instrument-info",
            "RadInstrumentManufacturerName": "Radiacode",
            "RadInstrumentIdentifier": self.serial_number,
            "RadInstrumentModelName": self.model,
            "RadInstrumentClassCode": "Spectroscopic Personal Radiation Detector",
            "RadInstrumentVersion": [
                {"RadInstrumentComponentName": "Radiacode-Firmware", "RadInstrumentComponentVersion": "unknown"},
                {"RadInstrumentComponentName": "Radiacode-App", "RadInstrumentComponentVersion": "unknown"},
                {"RadInstrumentComponentName": "Radiacode-Python", "RadInstrumentComponentVersion": radiacode_ver},
                {"RadInstrumentComponentName": "Radiacode-Tools", "RadInstrumentComponentVersion": rctools_ver},
            ],
        }
        return self._populate_rad_detector_information()

    def _populate_rad_detector_information(self) -> bool:
        "Fill in the RadiationDectInformation element, mostly for the scintillator type"
        rdkc = "CsI"
        rdd = "CsI:Tl"
        if self.model.endswith("G"):
            rdkc = "GaGG"
            rdd = "GaGG:Ce"
        self.rad_detector_information = {
            "@id": self._rdi,
            "RadDetectorCategoryCode": "Gamma",
            "RadDetectorKindCode": rdkc,
            "RadDetectorDescription": f"{rdd} scintillator, coupled to SiPM",
            "RadDetectorLengthValue": {"@units": "mm", "#text": "10"},
            "RadDetectorWidthValue": {"@units": "mm", "#text": "10"},
            "RadDetectorDepthValue": {"@units": "mm", "#text": "10"},
            "RadDetectorVolumeValue": {"@units": "cc", "#text": "1"},
        }
        return True

    def load_file(self, filename: str) -> None:
        """
        Read an N42 File

        Use this to read from the filesystem
        """
        with open(filename, "rt") as ifd:
            self.load_data(ifd.read())

    def load_data(self, data) -> None:
        """
        Process N42 data, with some radiacode-specific assumptions

        Use this function if you're passing in a string or file object.
        """
        n42_data = xmltodict.parse(data, dict_constructor=dict)["RadInstrumentData"]

        self.uuid = n42_data["@n42DocUUID"]
        self._populate_rad_instrument_information(n42_data["RadInstrumentInformation"]["RadInstrumentIdentifier"])

        # XML transports entities as a dict for a single item, or a list of dicts. Ugh.
        if isinstance(n42_data["EnergyCalibration"], list):
            energy_calibrations = {x["@id"]: x["CoefficientValues"] for x in n42_data["EnergyCalibration"]}
        else:
            energy_calibrations = {
                n42_data["EnergyCalibration"]["@id"]: n42_data["EnergyCalibration"]["CoefficientValues"]
            }

        if isinstance(n42_data["RadMeasurement"], list):
            rmz = n42_data["RadMeasurement"]
        else:
            rmz = [n42_data["RadMeasurement"]]

        for rm in rmz:
            sl = self._spectrum_layer_from_rad_measurement(rm, energy_calibrations)
            mc = rm["MeasurementClassCode"]
            if mc == "Foreground":
                self.spectrum_data.fg_spectrum = sl
            elif mc == "Background":
                self.spectrum_data.bg_spectrum = sl
            else:
                raise ValueError

    def generate_xml(self, dest=None) -> str:
        """
        Export the in-memory representation to XML

        dest can be a file-like object, and if not given a string representation will be returned.
        """
        if not self.uuid:
            self.uuid = str(uuid4())

        data = self.header.copy()
        data["@n42DocUUID"] = self.uuid
        data["RadInstrumentInformation"] = self.rad_instrument_information
        data["RadDetectorInformation"] = self.rad_detector_information
        if not isinstance(self.spectrum_data.fg_spectrum.calibration, EnergyCalibration):
            raise ValueError("No foreground calibration")
        data["EnergyCalibration"] = [
            {
                "@id": "ec-fg",
                "CoefficientValues": " ".join([f"{x:f}" for x in self.spectrum_data.fg_spectrum.calibration.values()]),
            },
        ]
        data["RadMeasurement"] = [
            self._rad_measurement_from_spectrum_layer(self.spectrum_data.fg_spectrum, fg=True),
        ]

        if isinstance(self.spectrum_data.bg_spectrum, SpectrumLayer):
            if not isinstance(self.spectrum_data.bg_spectrum.calibration, EnergyCalibration):
                raise ValueError("No background calibration")

            data["EnergyCalibration"].append(
                {
                    "@id": "ec-bg",
                    "CoefficientValues": " ".join(
                        [f"{x:f}" for x in self.spectrum_data.bg_spectrum.calibration.values()]
                    ),
                }
            )
            data["RadMeasurement"].append(
                self._rad_measurement_from_spectrum_layer(self.spectrum_data.bg_spectrum, fg=False)
            )

        return xmltodict.unparse({"RadInstrumentData": data}, output=dest, pretty=True)

    def write_file(self, filename: str) -> None:
        "Write an N42 file"
        with open(filename, "wt") as ofd:
            self.generate_xml(ofd)

    def to_rcspectrum(self) -> RcSpectrum:
        return self.spectrum_data

    def from_rcspectrum(self, s: RcSpectrum) -> bool:
        "Pass in a dual layer spectrum if you want a dual layer N42 output"
        self.uuid = s.uuid()
        self.spectrum_data = s
        self._populate_rad_instrument_information(s.fg_spectrum.serial_number)  # type:ignore
        return True
        return True
