#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
Interfaces to Radiacode File Formats: tracks, spectra, spectrograms, and N42 conversion
"""

from binascii import hexlify, unhexlify
from datetime import datetime, timedelta
from hashlib import sha256
from re import sub as re_sub
from struct import pack as struct_pack
from struct import unpack as struct_unpack
from typing import Any, Dict, List, Optional
from uuid import uuid4

import xmltodict

from rctypes import EnergyCalibration, SpectrogramPoint, SpectrumLayer, TrackPoint
from rcutils import DateTime2FileTime, FileTime2DateTime

# there's enough datetime mangling that it's worth making a few helpers
_datestr: str = "%Y-%m-%d %H:%M:%S"
_datestr_T: str = _datestr.replace(" ", "T")


def _parse_datetime(ds: str, fmt: str = _datestr) -> datetime:
    return datetime.strptime(ds, fmt)


def _format_datetime(dt: datetime, fmt: str = _datestr) -> str:
    return dt.strftime(fmt)


class RcTrack:
    "Radiacode Track (.rctrk) interface"

    def __init__(self, filename: Optional[str] = None) -> None:
        self._clear_data()
        self._columns = ["DateTime", "Latitude", "Longitude", "Accuracy", "DoseRate", "CountRate", "Comment"]
        self.filename = filename
        if filename:
            self.load_file(filename)

    def _clear_data(self) -> None:
        "Clear out the header, in preparation for loading"
        self.name: str = ""
        self.serialnumber: str = ""
        self.comment: str = ""
        self.flags: str = ""
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
                    "datetime": datetime(),
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
        for p in d["points"]:
            if isinstance(p[1], str):
                p[1] = _parse_datetime(p[1])
            for i in range(2, 7):
                p[i] = float(p[i])
        self.points = [TrackPoint(*x[1:]) for x in d["points"]]
        return True

    def _format_trackpoint(self, tp: TrackPoint):
        fz = [None] + list(tp._asdict().values())
        fz[0] = DateTime2FileTime(fz[1])
        fz[1] = _format_datetime(fz[1])
        return "\t".join([str(x) for x in fz])

    def write_file(self, filename: str) -> None:
        "Write the in-memory representation to filesystem"
        with open(filename, "wt") as ofd:
            print("Track: " + "\t".join([self.name, self.serialnumber, self.comment, self.flags]), file=ofd)
            # Patch column names in output file.
            print("\t".join(["Timestamp", "Time"] + self._columns[1:]), file=ofd)
            for p in self.points:
                print(self._format_trackpoint(p), file=ofd)

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
                fields = line.split("\t")
                if len(fields) != nf + 1:
                    raise ValueError(f"Incorrect number of values on line {n+1}")
                fields[1] = FileTime2DateTime(fields[0])  # filetime is higher resolution than YYYY-mm-dd HH:MM:SS
                for i in range(2, 7):
                    fields[i] = float(fields[i])
                    pass
                fields[-1] = fields[-1].rstrip("\n")
                self.points.append(TrackPoint(*fields[1:]))

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
                time=dt,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy,
                dose_rate=dose_rate,
                count_rate=count_rate,
                comment=comment,
            )
        )


class RcSpectrum:
    "Radiacode Spectrum (.xml)"

    def __init__(self, filename: str = None) -> None:
        self.fg_spectrum: Optional[SpectrumLayer] = None
        self.bg_spectrum: Optional[SpectrumLayer] = None
        self.note: str = ""

        if filename:
            self.load_file(filename)

    def __repr__(self):
        return "Spectrum(" f"\n\tfg={self.fg_spectrum}" f"\n\tbg={self.bg_spectrum}" f'\n\tnote="{self.note}"\n)'

    def _parse_spectrum(self, spectrum: Dict[str, Any]) -> SpectrumLayer:
        """Given an spectrum dict, return useful items"""
        coeffs = [float(f) for f in spectrum["EnergyCalibration"]["Coefficients"]["Coefficient"]]
        polynomial_order = int(spectrum["EnergyCalibration"]["PolynomialOrder"])

        rv = SpectrumLayer(
            spectrum_name=spectrum["SpectrumName"],
            device_model="",
            serial_number=spectrum.get("SerialNumber", None),
            calibration=EnergyCalibration(*coeffs),
            duration=int(spectrum["MeasurementTime"]),
            channels=int(spectrum["NumberOfChannels"]),
            counts=[int(i) for i in spectrum["Spectrum"]["DataPoint"]],
        )

        if len(rv.counts) != rv.channels:
            raise ValueError("spectrum length != number of channels")

        if 2 != polynomial_order:
            raise ValueError("invalid calibration order")

        if len(coeffs) != polynomial_order + 1:
            raise ValueError("Inconsistent calibration polynomial")

        return rv

    def load_file(self, filename: str) -> None:
        with open(filename) as ifd:
            self.load_str(ifd.read())

    def load_str(self, data: str) -> None:
        sp = xmltodict.parse(data, dict_constructor=dict)["ResultDataFile"]["ResultDataList"]["ResultData"]

        tmp = sp["EnergySpectrum"]  # explode if the spectrum is missing. No foreground = not useful
        self.fg_spectrum = self._parse_spectrum(tmp)._replace(device_model=sp["DeviceConfigReference"]["Name"])

        try:
            tmp = sp.get("BackgroundEnergySpectrum")
            self.bg_spectrum = self._parse_spectrum(tmp)
        except (KeyError, AttributeError, TypeError):
            tmp = None

        # older versions of data files don't have start and end times
        if tmp:
            try:
                a = [_parse_datetime(s, _datestr_T) for s in sp.get("StartTime", None)]
                b = [_parse_datetime(s, _datestr_T) for s in sp.get("EndTime", None)]
                self.fg_spectrum = self.fg_spectrum._replace(timestamp=a[0], duration=b[0] - a[0])
                self.bg_spectrum = self.bg_spectrum._replace(timestamp=a[1], duration=b[1] - a[1])
            except (KeyError, TypeError, AttributeError):
                pass
        else:
            try:
                a = _parse_datetime(sp.get("StartTime", None), _datestr_T)
                b = _parse_datetime(sp.get("EndTime", None), _datestr_T)
                d = b - a
                self.fg_spectrum = self.fg_spectrum._replace(timestamp=a, duration=d)
            except (KeyError, TypeError, AttributeError):
                pass

    def _spec_layer_to_elements(self, bg=False) -> List[str]:
        sl: SpectrumLayer = self.bg_spectrum if bg is True else self.fg_spectrum
        sc = sl.comment if sl.comment else ""
        st = sl.timestamp
        et = sl.timestamp + sl.duration

        b = "Background" if bg else ""
        rv = [
            f"<StartTime>{st.strftime(_datestr_T)}</StartTime>",
            f"<EndTime>{et.strftime(_datestr_T)}</EndTime>\n",
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
            *[f"\t<Coefficient>{k}</Coefficient>" for k in sl.calibration],
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
        rv = {
            "fg": self.fg_spectrum._asdict(),
            "bg": None,
            "note": self.note,
        }
        if self.bg_spectrum:
            rv["bg"] = (self.bg_spectrum._asdict(),)

        rv["fg"]["timestamp"] = str(rv["fg"]["timestamp"])
        rv["fg"]["duration"] = rv["fg"]["duration"].total_seconds()
        if rv["bg"]:
            rv["bg"]["timestamp"] = str(rv["bg"]["timestamp"])
            rv["bg"]["duration"] = rv["bg"]["duration"].total_seconds()
        return rv

    def _make_layer_from_dict(self, d: Dict[str, Any]) -> SpectrumLayer:
        rv = None
        try:
            rv = SpectrumLayer(
                spectrum_name=d["spectrum_name"],
                device_model=d["device_model"],
                serial_number=d["serial_number"],
                calibration=EnergyCalibration(d["calibration"]),
                timestamp=datetime.strptime(d["timestamp"], _datestr),
                duration=timedelta(seconds=float(d["duration"])),
                channels=int(d["channels"]),
                counts=[int(i) for i in d["counts"]],
            )
        except Exception:
            pass
        return rv

    def from_dict(self, d: Dict[str, Any]) -> None:
        self.note = d.get("note", "")
        self.fg_spectrum = self._make_layer_from_dict(d["fg"])
        if len(self.fg_spectrum.counts) != self.fg_spectrum.channels:
            raise ValueError("Inconsistent channel counts in foreground")

        bg = self._make_layer_from_dict(d["bg"])
        if bg:
            self.bg_spectrum = bg
            if len(self.bg_spectrum.counts) != self.bg_spectrum.channels:
                raise ValueError("Inconsistent channel counts in background")

    def uuid(self) -> str:
        "generate a uuid-shaped string based on the content of the spectrum file"
        h = sha256(str(self).encode()).hexdigest()[:32]
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


class RcSpectrogram:
    "Radiacode Spectrogram (.rcspg)"

    def __init__(self) -> None:
        self.name: str = ""
        self.timestamp: datetime = None
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
        self.delta_point: SpectrogramPoint = SpectrogramPoint()
        # and this is what it's really for: counts at a particular time.
        self.samples: List[SpectrogramPoint] = []

    def __repr__(self) -> str:
        s = " " + self.comment if self.comment else ""
        return (
            f"Spectrogram(\n\tname:'{self.name}',"
            f"\n\ttime:'{self.timestamp}',"
            f"\n\tsn:{self.serial_number},"
            f"\n\t{self.calibration},"
            f"\n\taccumulaton:{self.accumulation_time}s,"
            f"\n\tnch={self.channels},"
            f"\n\tcomment:'{s}'"
            f"\n\tn={len(self.samples)})"
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
        tstr = _format_datetime(self.timestamp)

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
        self.calibration = EnergyCalibration(*tmp[1:4])
        self.historical_spectrum = SpectrogramPoint(timedelta=timedelta(seconds=tmp[0]), counts=tmp[4:])

    def _make_historical_spectrum_line(self) -> str:
        """
        The second line of the spectrogram is the spectrum of the accumulated exposure
        since last data reset.
        (duration:int, coeffs:float[3], counts:int[1024])
        """
        v = struct_pack(
            f"<Ifff{len(self.historical_spectrum.counts)}I",
            int(self.historical_spectrum.timedelta.total_seconds()),
            *self.calibration,
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
                    tmp = [int(x) for x in line.strip().split()]
                    dt = FileTime2DateTime(tmp.pop(0))
                    td = timedelta(seconds=tmp.pop(0))
                    self.samples.append(SpectrogramPoint(dt, td, tmp))

    def _make_spectrogram_line(self, l: SpectrogramPoint) -> str:
        """
        Format a SpectrogramPoint as line for the rcspg
        """
        rv = [DateTime2FileTime(l.timestamp), int(l.timedelta.total_seconds())]
        rv.extend(l.counts)
        rv = "\t".join([str(x) for x in rv])
        rv = re_sub(r"(\s0)+$", "", rv)
        return rv

    def add_point(self, counts: List[int], timestamp: Optional[datetime] = None) -> bool:
        """
        Add a datapoint to the spectrogram.

        Counts should be raw measurements from the device. This function takes
        care of computing the difference. Returns True if a point was added to
        history, False otherwise. If not given, timestamp is set to the system
        time.
        """
        if timestamp is None:
            timestamp = datetime.now()
        if self.delta_point is None:
            self.delta_point = SpectrogramPoint(timestamp=timestamp, counts=counts)
            return False

        dx = [z[0] - z[1] for z in zip(counts, self.delta_point.counts)]
        self.samples.append(
            SpectrogramPoint(timestamp=timestamp, timedelta=timestamp - self.delta_point.timestamp, counts=dx)
        )
        self.delta_point = SpectrogramPoint(time=timestamp, counts=counts)
        return True

    def write_file(self, filename: str) -> None:
        "Dump the spectrogram to a file"
        if not self.accumulation_time:
            self.accumulation_time = self.samples[-1].timestamp - self.samples[0].timestamp
        with open(filename, "wt") as ofd:
            print(self._make_header_line(), file=ofd)
            print(self._make_historical_spectrum_line(), file=ofd)
            for s in self.samples:
                print(self._make_spectrogram_line(s), file=ofd)


class RcN42:
    "Minimal N42 implementation that can transcode to/from dual layer RadiaCode XML spectrum"
    rad_detector_information: Dict[str, Any] = {}
    rad_instrument_information: Dict[str, Any] = {}
    _rdi: str = "radiacode-scinitillator-sipm"

    def __init__(self, filename: str = None) -> None:
        self.serial_number: str = ""
        self.model: str = ""
        self.header: Dict[str, str] = {}
        self.uuid: str = ""
        self.spectrum_data: RcSpectrum = RcSpectrum()

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
        ec = EnergyCalibration(*[float(x) for x in ecz[rm["Spectrum"]["@energyCalibrationReference"]].split()])
        counts = [int(x) for x in rm["Spectrum"]["ChannelData"]["#text"].split()]

        return SpectrumLayer(
            spectrum_name=rm["Remark"].replace("Title: ", ""),
            device_model=self.model,
            serial_number=self.serial_number,
            calibration=ec,
            timestamp=_parse_datetime(rm["StartDateTime"], _datestr_T),
            duration=timedelta(seconds=int(rm["RealTimeDuration"].strip("PTS"))),
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

    def _populate_rad_instrument_information(self, serial_number: str = None) -> bool:
        "Fill in the RadiationInstrumentInformation element, mostly for the scintillator type"
        if serial_number is None and self.serial_number is None:
            raise ValueError
        if serial_number:
            self.serial_number = serial_number
        self.model = f"RadiaCode-{self.serial_number.split('-')[1]}"

        self.rad_instrument_information = {
            "@id": "radiacode-instrument-info",
            "RadInstrumentManufacturerName": "Radiacode",
            "RadInstrumentIdentifier": self.serial_number,
            "RadInstrumentModelName": self.model,
            "RadInstrumentClassCode": "Spectroscopic Personal Radiation Detector",
            "RadInstrumentVersion": [
                {"RadInstrumentComponentName": "Radiacode-Firmware", "RadInstrumentComponentVersion": "unknown"},
                {"RadInstrumentComponentName": "Radiacode-App", "RadInstrumentComponentVersion": "unknown"},
                {"RadInstrumentComponentName": "Radiacode-Tools", "RadInstrumentComponentVersion": "0.1.2"},
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
            self.uuid = uuid4()

        data = self.header.copy()
        data["@n42DocUUID"] = self.uuid
        data["RadInstrumentInformation"] = self.rad_instrument_information
        data["RadDetectorInformation"] = self.rad_detector_information
        data["EnergyCalibration"] = [
            {
                "@id": "ec-fg",
                "CoefficientValues": " ".join([f"{x:f}" for x in self.spectrum_data.fg_spectrum.calibration]),
            },
        ]
        data["RadMeasurement"] = [
            self._rad_measurement_from_spectrum_layer(self.spectrum_data.fg_spectrum, fg=True),
        ]

        if self.spectrum_data.bg_spectrum:
            data["EnergyCalibration"].append(
                {
                    "@id": "ec-bg",
                    "CoefficientValues": " ".join([f"{x:f}" for x in self.spectrum_data.bg_spectrum.calibration]),
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
        self.uuid = s.uuid()
        self.spectrum_data = s
        self._populate_rad_instrument_information(s.fg_spectrum.serial_number)
        return True
