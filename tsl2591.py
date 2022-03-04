import time
import smbus # pylint: disable=import-error

DEVICE_ADDRESS              = 0x29

COMMAND_NORMAL              = 0xA0
COMMAND_CLEAR_INT           = 0xE6
COMMAND_CLEAR_ALL           = 0xE7
COMMAND_FORCE_INT           = 0xE4

REGISTER_ENABLE             = 0x00
REGISTER_CONTROL            = 0x01
REGISTER_AILTL              = 0x04
REGISTER_AILTH              = 0x05
REGISTER_AIHTL              = 0x06
REGISTER_AIHTH              = 0x07
REGISTER_NPAILTL            = 0x08
REGISTER_NPAILTH            = 0x09
REGISTER_NPAIHTL            = 0x0A
REGISTER_NPAIHTH            = 0x0B
REGISTER_PERSIST            = 0x0C
REGISTER_PACKAGE            = 0x11
REGISTER_ID                 = 0x12
REGISTER_STATUS             = 0x13
REGISTER_C0DATAL            = 0x14
REGISTER_C0DATAH            = 0x15
REGISTER_C1DATAL            = 0x16
REGISTER_C1DATAH            = 0x17

ENABLE_POWEROFF             = 0xD0
ENABLE_POWERON              = 0x01
ENABLE_AEN                  = 0x02
ENABLE_AIEN                 = 0x10
ENABLE_SAI                  = 0x40
ENABLE_NPIEN                = 0x80

STATUS_NPINTR               = 0x20
STATUS_AINT                 = 0x10
STATUS_AVALID               = 0x01

PERSIST_EVERY               = 0x00
PERSIST_ANY                 = 0x01
PERSIST_2                   = 0x02
PERSIST_3                   = 0x03
PERSIST_5                   = 0x04
PERSIST_10                  = 0x05
PERSIST_15                  = 0x06
PERSIST_20                  = 0x07
PERSIST_25                  = 0x08
PERSIST_30                  = 0x09
PERSIST_35                  = 0x0A
PERSIST_40                  = 0x0B
PERSIST_45                  = 0x0C
PERSIST_50                  = 0x0D
PERSIST_55                  = 0x0E
PERSIST_60                  = 0x0F

CONTROL_AGAIN_LOW           = 0x00
CONTROL_AGAIN_MED           = 0x10
CONTROL_AGAIN_HIGH          = 0x20
CONTROL_AGAIN_MAX           = 0x30
CONTROL_ATIME_100MS         = 0x00
CONTROL_ATIME_200MS         = 0x01
CONTROL_ATIME_300MS         = 0x02
CONTROL_ATIME_400MS         = 0x03
CONTROL_ATIME_500MS         = 0x04
CONTROL_ATIME_600MS         = 0x05

MAX_COUNT_100MS             = 36863
MAX_COUNT                   = 65535

LUX_DF                      = 408.0
LUX_COEFB                   = 1.64
LUX_COEFC                   = 0.59
LUX_COEFD                   = 0.86

class TSL2591(object):
    def __init__(self, dev=DEVICE_ADDRESS, bus=1, interrupt=False,
        np_interrupt=False, sleep_after=False):
        """
        To enable the physical interrupt pin, either interrupt or np_interrupt
        must be set to True. The interrupt pin will be set to low whenever an
        interrupt is asserted.

        Args:
            dev: the device address on the i2c bus.
            bus: the i2c bus.
            interrupt: enables or disables interrupts.
            np_interrupt: enables or disables non-persist interrupts.
            sleep_after: enables or disables the sleep after interrupt feature.
        Attributes:
            _wait: the amount of time in seconds between data cycles.
            _next: a timestamp used for syncing data access with data cycles.
            _again: used for calculating lux.
            _atime: used for calculating lux.
            saturated: True if sensor is saturated, False if not.
        Raises:
            RuntimeError: if device ID does not match or can not be obtained.
        """

        self._bus = smbus.SMBus(bus)
        self._dev = dev
        self._aien = interrupt
        self._npien = np_interrupt
        self._sai = sleep_after

        if not self.is_tsl2591:
            raise RuntimeError('unsupported device')

        self.time = CONTROL_ATIME_100MS
        self.gain = CONTROL_AGAIN_LOW
        self.saturated = False

        self._next = time.time() + self._wait
        
    def on(self):
        """Turns the sensor on, does not control power to device."""

        enable = 0
        enable |= ENABLE_AIEN if self._aien else False
        enable |= ENABLE_NPIEN if self._npien else False
        enable |= ENABLE_SAI if self._sai else False

        self._write_byte(REGISTER_ENABLE, ENABLE_POWERON | ENABLE_AEN)
        self._write_byte(REGISTER_ENABLE, ENABLE_POWERON | ENABLE_AEN | enable)
        self.clear_interrupt() # Must clear interrupt if not reset

        while not self.is_valid:
            time.sleep(self._wait)

        self._next = time.time() + self._wait

    def off(self):
        """Turns the sensor off, does not control power to device."""

        self._write_byte(REGISTER_ENABLE, ENABLE_POWEROFF)

    def reset(self):
        """
        Shorthand function for turning the sensor off, then turning the sensor
        back on. The device must be reset whenever changing interrupt
        thresholds.
        """

        self.off()
        self.on()

    @property
    def device(self):
        """
        A read-only property identifying the device. TSL2591 sensors will always
        return 0x50 or 80.
        """

        return self._read_byte(REGISTER_ID)

    @property
    def gain(self):
        """
        A configurable property controlling the sensor's analog gain. There are
        four valid modes:
            * Low: CONTROL_AGAIN_LOW or 0
            * Medium: CONTROL_AGAIN_MED or 16
            * High: CONTROL_AGAIN_HIGH or 32
            * Max: CONTROL_AGAIN_MAX or 48

        The higher the setting, the more sensitive the sensor is to light.
        Higher settings will easily saturate the sensor and should only be used
        in special cases.
        
        The device defaults to medium, but low is the default for this driver 
        and is recommended for normal light conditions.
        """
        
        return self._read_byte(REGISTER_CONTROL) & 0x30

    @gain.setter
    def gain(self, val):
        valid = (CONTROL_AGAIN_LOW, CONTROL_AGAIN_MED, CONTROL_AGAIN_HIGH,
            CONTROL_AGAIN_MAX)

        if val in valid:
            if (val == CONTROL_AGAIN_LOW):
                self._again = 1.0
            elif (val == CONTROL_AGAIN_MED):
                self._again = 25.0
            elif (val == CONTROL_AGAIN_HIGH):
                self._again = 428.0
            elif (val == CONTROL_AGAIN_MAX):
                self._again = 9876.0

            cur = self._read_byte(REGISTER_CONTROL) & 0xCF
            self._write_byte(REGISTER_CONTROL, cur | val)

    @property
    def time(self):
        """
        A configurable property controlling the sensor's integration time. There
        are six valid times:
            * 100ms: CONTROL_ATIME_100MS or 0
            * 200ms: CONTROL_ATIME_200MS or 1
            * 300ms: CONTROL_ATIME_300MS or 2
            * 400ms: CONTROL_ATIME_400MS or 3
            * 500ms: CONTROL_ATIME_500MS or 4
            * 600ms: CONTROL_ATIME_600MS or 5

        The higher the time, the longer the sensor's exposure to light. Higher
        settings will easily saturate the sensor and should only be used in
        special cases.
        
        The device defaults to 200ms, but this driver defaults to 100ms. Both
        are recommended for normal light conditions.

        The maximum count for 100 ms is reduced from 65535 to 36863.  Meaning
        the device will saturate at a lower value than other integration times.
        """

        return self._read_byte(REGISTER_CONTROL) & 0x07

    @time.setter
    def time(self, val):
        if val >= 0 and val <= 5:
            if (val == CONTROL_ATIME_100MS):
                self._atime = 100.0
            elif (val == CONTROL_ATIME_200MS):
                self._atime = 200.0
            elif (val == CONTROL_ATIME_300MS):
                self._atime = 300.0
            elif (val == CONTROL_ATIME_400MS):
                self._atime = 400.0
            elif (val == CONTROL_ATIME_500MS):
                self._atime = 500.0
            elif (val == CONTROL_ATIME_600MS):
                self._atime = 600.0

            self._wait = self._atime / 100 

            cur = self._read_byte(REGISTER_CONTROL) & 0xF8
            self._write_byte(REGISTER_CONTROL, cur | val)

    @property
    def raw_data(self):
        """
        A read-only property returning the raw sensor data using an internal
        unit of measure called counts. It will always return a tuple using the
        following structure: (full spectrum, infrared).

        If the sensor is saturated (the light is too intense for the sensor to
        measure accurately), the saturated property will be set to True.

        The visible light measurement can be calculated by subtracting the
        infrared value from the full spectrum value.
        """

        curr = time.time()

        if self._next > curr:
            time.sleep(self._next - curr)

        self._next = time.time() + self._wait

        # Read sequentially starting at lower byte address.
        ch0 = self._read_word(REGISTER_C0DATAL)
        ch1 = self._read_word(REGISTER_C1DATAL)

        # Quick fix to detect saturation
        maxc = MAX_COUNT_100MS if self.time == 0 else MAX_COUNT
        self.saturated = True if ch0 > maxc or ch1 > maxc else False

        return (ch0, ch1)

    @property
    def lux(self):
        """
        A read-only property returning the sensor's measurement in lux. The
        correct method of calcuating lux for this device is undocumented. Any
        values returned by this function should be assumed to be incorrect until
        further testing has been done.
        """

        ch0, ch1 = self.raw_data
        cpl = (self._atime * self._again) / LUX_DF

        # Adafruit's current method for calculating Lux
        # from https://github.com/adafruit/Adafruit_TSL2591_Library
        lux = (ch0 - ch1) * (1.0 - (ch1 / ch0)) / cpl if ch0 > 0 else 0

        # Adafruit's alternative calculation
        '''
        lux = (ch0 - 1.7 * ch1) / cpl
        '''

        # Adafruit's old calcuation
        '''
        l1 = (ch0 - LUX_COEFB * ch1) / cpl
        l2 = (LUX_COEFC * ch0 - LUX_COEFD * ch1) / cpl
        
        lux = max(l1, l2)
        '''

        return lux

    @property
    def interrupt(self):
        """
        A configurable property of the device's interrupt thresholds. The format
        is a tuple: (low threshold, high threshold).

        Low threshold: triggers interrupt if full spectrum count is below this
            value.

        High threshold: triggers interrupt if full spectrum count
            is above this value.

        Both threshold values are measured in counts and only the full spectrum
        measurement is evaluated.
        """

        l = self._read_word(REGISTER_AILTL)
        h = self._read_word(REGISTER_AIHTL)

        return (l, h)

    @interrupt.setter
    def interrupt(self, val):
        self._write_word(REGISTER_AILTL, int(val[0]))
        self._write_word(REGISTER_AIHTL, int(val[1]))
            
    @property
    def persist(self):
        return self._read_word(REGISTER_PERSIST)

    @persist.setter
    def persist(self, val):
        """
        A property of the device's persist setting used for evaluating
        interrupts, does not affect non-persist interrupts. There are 16 valid
        persist intervals:
            * Every data cycle: PERSIST_EVERY or 0
            * Any value outside of threshold range: PERSIST_ANY or 1
            * 2 consecutive values out of range: PERSIST_2 or 2
            * 3 consecutive values out of range: PERSIST_3 or 3
            * 5 consecutive values out of range: PERSIST_5 or 4
            * 10 consecutive values out of range: PERSIST_10 or 5
            * 15 consecutive values out of range: PERSIST_15 or 6
            * 20 consecutive values out of range: PERSIST_20 or 7
            * 25 consecutive values out of range: PERSIST_25 or 8
            * 30 consecutive values out of range: PERSIST_30 or 9
            * 35 consecutive values out of range: PERSIST_35 or 10
            * 40 consecutive values out of range: PERSIST_40 or 11
            * 45 consecutive values out of range: PERSIST_45 or 12
            * 50 consecutive values out of range: PERSIST_50 or 13
            * 55 consecutive values out of range: PERSIST_55 or 14
            * 60 consecutive values out of range: PERSIST_60 or 15

        The device defaults to PERSIST_EVERY, meaning an interrupt with always
        be triggered unless you changed the persist interval or only use
        non-persist interrupts.

        The thresholds are evaluated per data cycle and not by time. Persist is
        affected by integration time (time it takes to complete a data cycle).
        """

        self._write_word(REGISTER_PERSIST, val)

    @property
    def np_interrupt(self):
        """Refer to the interrupt property."""

        l = self._read_word(REGISTER_NPAILTL)
        h = self._read_word(REGISTER_NPAIHTL)

        return (l, h)

    @np_interrupt.setter
    def np_interrupt(self, val) :
        self._write_word(REGISTER_NPAILTL, val[0])
        self._write_word(REGISTER_NPAIHTL, val[1])

    @property
    def interrupt_enabled(self):
        """A read-only property. True if interrupts are enabled."""

        return bool((self._read_byte(REGISTER_ENABLE) & ENABLE_AIEN) >> 4)

    @property
    def np_interrupt_enabled(self):
        """A read-only property. True if non-persist interrupts are enabled."""

        return bool((self._read_byte(REGISTER_ENABLE) & ENABLE_NPIEN ) >> 6)

    @property
    def sleep_after_enabled(self):
        """
        A read-only property. True if the sleep after interrupt feature is
        enabled.
        """

        return bool((self._read_byte(REGISTER_ENABLE) & ENABLE_SAI) >> 5)

    @property
    def is_on(self):
        """A read-only property. True if sensor is turned on."""

        return bool(self._read_byte(REGISTER_ENABLE) & ENABLE_POWERON)

    # ALS Valid. Indicates that the ADC channels have completed an
    # integration cycle since the AEN bit was asserted.
    @property
    def is_valid(self):
        """
        A read-only property. True if device has completed a data cycle since
        turning the sensor on or resetting the device.
        """

        return bool(self._read_byte(REGISTER_STATUS) & STATUS_AVALID)

    # ALS Interrupt. Indicates that the device is asserting an ALS
    # interrupt.
    @property
    def is_interrupt(self):
        """A read-only property. True if an interrupt has been triggered."""

        return bool((self._read_byte(REGISTER_STATUS) & STATUS_AINT) >> 4)

    # No-persist Interrupt. Indicates that the device has encountered a
    # no-persist interrupt condition.
    @property
    def is_np_interrupt(self):
        """
        A read-only property. True if a non-persist interrupt has been
        triggered.
        """

        return bool((self._read_byte(REGISTER_STATUS) & STATUS_NPINTR) >> 5)

    @property
    def is_tsl2591(self):
        """A read-only property. True if device is a TSL2591 sensor."""

        try:
            if self.device == 0x50:
                return True
        except:
            return False

    def force_interrupt(self):
        """Forces an interrupt even if thresholds have not been exceeded."""

        self._read_byte(COMMAND_FORCE_INT)

    def clear_interrupt(self):
        """
        Clears and resets ALS interrupt but does not reset interrupt thresholds.
        """

        self._write_byte(REGISTER_ENABLE, 3)
        self._write_byte(REGISTER_ENABLE, 19)
        self._read_byte(COMMAND_CLEAR_INT)

    def clear_all_interrupts(self):
        """
        Clears all interrupts but does not reset interrupt thresholds. Persist
        values seem to be ignored after calling this.
        """

        self._read_byte(COMMAND_CLEAR_ALL)

    def system_reset(self):
        """This is basically a hard reset, also turns the sensor off."""

        # Throws a Remote I/O error. Could be caused by the device resetting or
        # something being done incorrectly.  Either way, this works.
        try:
            self._write_byte(REGISTER_CONTROL, 0x80)
        except OSError as code:
            if str(code) == '121':
                pass
            else:
                raise

    def _read_byte(self, reg):
        return self._bus.read_byte_data(self._dev, COMMAND_NORMAL | reg)

    def _read_word(self, reg):
        return self._bus.read_word_data(self._dev, COMMAND_NORMAL | reg)

    def _write_byte(self, reg, msg):
        self._bus.write_byte_data(self._dev, COMMAND_NORMAL | reg, msg) 

    def _write_word(self, reg, msg):
        self._bus.write_word_data(self._dev, COMMAND_NORMAL | reg, msg)
