# Radiacode Tools

Just some things for working with my RadiaCode-102 from Scan-Electronics.

### calibrate.py
This tool computes calibration factors for mapping the channel to detected
photon energy. 

Use `calibrate.py -W` to generate a example calibration file, then use your
detector to measure a range of photon energies.

```
usage: calibrate.py [-h] [-z] [-f FILE] [-o N] [-p N] [-W]

options:
  -h, --help                   show this help message and exit
  -z, --zero-start             Add a synthetic (0,0) calibration data point
  -f FILE, --cal-file FILE     Calibration data file [radiacode.json]
  -o N, --order N              Calibration polynomial order [2]
  -p N, --precision N          Number of decimal places in calibration factors [8]
  -W, --write-template         Generate a template calibration file

```

Calibration can be performed with a single sample (Th-232, Ra-226), though better
results may be obtained using more isotopes with a broader range of energies.

```
# data derived from americium, barium, europium, potassium, radium, sodium, and thorium.
$ ./calibrate.py 
data range: (9, 26) - (941, 2614)
x^0 .. x^2: [-7.26773237, 2.44338618, 0.00037684]
R^2: 0.99988

# Same data as above, but with a synthetic (0,0) data point
$ ./calibrate.py -z
data range: (0, 0) - (941, 2614)
x^0 .. x^2: [-6.28323127, 2.43830549, 0.00038176]
R^2: 0.99988

# Single source calibration using thoriated tungsten welding electrodes
$ ./calibrate.py -f thorium.json 
data range: (138, 338) - (941, 2614)
x^0 .. x^2: [-15.63118352, 2.47761651, 0.00033984]
R^2: 0.99988

# Single source calibration using a luminous radium paint 
$ ./calibrate.py -f radium.json 
data range: (122, 295) - (802, 2204)
x^0 .. x^2: [-2.45705927, 2.39432185, 0.00044401]
R^2: 0.99998
```

### n42convert.py
This tool converts a RadiaCode ("RC") spectrum XML file into
[ANSI N42](https://www.nist.gov/pml/radiation-physics/ansiieee-n4242-2020-version)
format for analysis with other tooling such as
[InterSpec](https://github.com/sandialabs/InterSpec)

```
usage: n42convert.py [-h] -f FILE [-b FILE] [-o FILE] [--overwrite] [-u UUID]

options:
  -h, --help                    show this help message and exit
  -f FILE, --foreground FILE    primary source data file
  -b FILE, --background FILE    Retrieve background from this file, using the background series if it exists or the main series otherwise.
  -o FILE, --output FILE        [<foreground>.n42]
  --overwrite                   allow existing file to be overwritten
  -u UUID, --uuid UUID          specify a UUID for the generated document. [<random>]
```

Only a single `-f` or `--foreground` argument is required. This will convert the
contents of an RC spectrum file into an N42 file named similarly to the source file.
If the RC file contains an included background spectrum it will be included in the
output.

In cases where two separate spectra have been recorded, they can be combined to form
a recording with included background. Consider a basement lab with a smoke detector;
the background radiation may be influenced by the concrete foundation made with an
aggregate containing a relatively large amount of thorium and uranium, there may be
elevated levels of radon due to poor ventilation, and the smoke detector contains an
americium source.

A recording of this ambient radiation can be saved as `lab.xml`.
When a new sample arrives, perhaps a container of sodium-free salt substitute (`KCl`)
or a crate of bananas for scale, it is measured in the same location as the lab
reference measurement, and the recording may be saved as `k40.xml`. These two files
may be merged by running `n42convert.py -f k40.xml -b lab.xml -o banana.n42`.

If the background RC file has both foreground and background spectra, the background
spectrum will be copied into the output N42 file. If no background spectrum exists,
the foreground data from the background file will be copied into the output N42 file.