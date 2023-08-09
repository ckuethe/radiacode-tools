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