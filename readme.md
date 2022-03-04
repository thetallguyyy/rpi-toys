# Basic i2c drivers for my Raspberry Pi

I wrote these because the other versions did not support interrupts. I have not
touched these files in years.

**Requirements**
```
smbus-cffi
```

## SHT-31
This is a common temperature and humidity sensor.

**Example**
```python
import time
import sht31

sensor = sht31.SHT31()

sensor.repeatability = sht31.REPEATABILITY_HIGH
sensor.periodic_interval = sht31.PERIODIC_MPS0

# Interrupt thresholds (optional)
sensor.high_alert_set = (90, 90)
sensor.high_alert_clear = (87, 87)
sensor.low_alert_set = (45, 30)
sensor.low_alert_clear = (50, 35)

sensor.periodic_mode = True

while True:
    temp, humd = sensor.periodic_fetch
    print(f'{round(temp, 1)} F {round(humd, 1} %')
    time.sleep(1)
```

See the included datasheet for more information.

## TSL2591
This is a light sensor. The values it returns are undocumented (you won't use
this thing for measuring light, more like intensity). Interrupts are useful.

**Example**
```python
import time
import tsl2591

sensor = tsl2591.TSL2591(interrupt=True)
sensor.system_reset()

sensor.interrupt = (0, 450) # triggers interrupt when light falls to this threshold
sensor.persist = tsl2591.PERSIST_60
sensor.gain = sensor.CONTROL_AGAIN_MED
sensor.time = sensor.CONTROL_ATIME_100MS

while True:
    full, ir = self.sensor.raw_data
    print(f'Full: {round(full, 1)} IR: {round(ir, 1}')
    time.sleep(1)

```

See the included datasheet for more information.
