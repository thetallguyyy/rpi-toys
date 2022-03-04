import time
import smbus # pylint: disable=import-error

DEVICE_ADDRESS              = (0x44, 0x45) # Alt. 0x45

# (MSB, LOW, MED, HIGH)
SINGLE_MODE                 = ((0x2C, 0x06, 0x0D, 0x10), # NO CLOCK STRETCH
                               (0x24, 0x00, 0x0B, 0x16)) # CLOCK STRETCH
PERIODIC_MODE               = ((0x20, 0x2F, 0x24, 0x32), # 0.5 MPS
                               (0x21, 0x2D, 0x26, 0x30), # 1.0 MPS
                               (0x22, 0x2B, 0x20, 0x36), # 2.0 MPS
                               (0x23, 0x29, 0x22, 0x34), # 4.0 MPS
                               (0x27, 0x2A, 0x21, 0x37)) # 10.0 MPS
# (MSB, LSB)
PERIODIC_FETCH              = (0xE0, 0x00)
PERIODIC_BREAK              = (0x30, 0x93)
PERIODIC_ART                = (0x2B, 0X32)
SOFT_RESET                  = (0x30, 0xA2)
CLEAR_STATUS                = (0x30, 0x41)
HEATER_ON                   = (0x30, 0x6D)
HEATER_OFF                  = (0x30, 0x66)
STATUS                      = (0xF3, 0x2D)

ALERT_HIGH_RSET             = (0xE1, 0x1F)
ALERT_HIGH_RCLEAR           = (0xE1, 0x14)
ALERT_LOW_RSET              = (0xE1, 0x09)
ALERT_LOW_RCLEAR            = (0xE1, 0x02)

ALERT_HIGH_WSET             = (0x61, 0x1D)
ALERT_HIGH_WCLEAR           = (0x61, 0x16)
ALERT_LOW_WSET              = (0x61, 0x0B)
ALERT_LOW_WCLEAR            = (0x61, 0x00)

#(RESET, LOW, MED, HIGH)
TIMING                      = (0.001, 0.004, 0.006, 0.015)

REPEATABILITY_LOW           = 1
REPEATABILITY_MED           = 2    
REPEATABILITY_HIGH          = 3
PERIODIC_MPS0               = 0
PERIODIC_MPS1               = 1
PERIODIC_MPS2               = 2
PERIODIC_MPS4               = 3
PERIODIC_MPS10              = 4
SCALE_FAHRENHEIT            = 0
SCALE_CELSIUS               = 1
CLOCK_STRETCH_DISABLE       = 0
CLOCK_STRETCH_ENABLE        = 1
CHECK_CRC_ENABLE            = True
CHECK_CRC_DISABLE           = False

class SHT31(object):
    def __init__(self, dev: int=DEVICE_ADDRESS[0], bus: int=1):
        """
        Args:
            dev: the device address on the i2c bus.
            bus: the i2c bus.
        Attributes:
            _periodic_wait: the amount of time in seconds it takes to measure
                data.
            _periodic_next: a timestamp used for syncing periodic fetches with 
                measurements.
        """

        self._bus = smbus.SMBus(bus)
        self._dev = dev
        self._periodic_next = None
        self._periodic_wait = None

        self.repeatability = REPEATABILITY_HIGH
        self.clock_stretch = False
        self.periodic_interval = PERIODIC_MPS1

    @property
    def single_shot(self):
        self._write_block(SINGLE_MODE[self.clock_stretch][0],
            [SINGLE_MODE[self.clock_stretch][self.repeatability]])

        time.sleep(TIMING[self.repeatability])

        block = self._read_block(SINGLE_MODE[self.clock_stretch][0], 6)

        return self._process_data(block)

    @property
    def periodic_mode(self):
        """
        A property of the device's periodic mode. If True, periodic mode is
        enabled. If False, it is disabled.
        """

        try:
            return self.__periodic_mode
        except AttributeError:
            return False

    @periodic_mode.setter
    def periodic_mode(self, val: bool):
        if val:
            self._write_block(PERIODIC_MODE[self.periodic_interval][0],
                [PERIODIC_MODE[self.periodic_interval][self.repeatability]])
            self._periodic_next = time.time() + self._periodic_wait + \
                TIMING[self.repeatability]
        else:
            self._write_block(PERIODIC_BREAK[0], [PERIODIC_BREAK[1]])
        
        self.__periodic_mode = val

    @property
    def periodic_interval(self):
        """
        A property of the device's periodic interval. There are five available
        intervals measured in mps (measurements per second):

            * 0.5 mps: PERIODIC_MPS0 or 0
            * 1 mps: PERIODIC_MPS1 or 1
            * 2 mps: PERIODIC_MPS2 or 2
            * 4 mps: PERIODIC_MPS4 or 3
            * 10 mps: PERIODIC_MPS10 or 4
        """

        return self.__periodic_interval

    @periodic_interval.setter
    def periodic_interval(self, val: int):
        if val >= 0 and val <= 4:

            # These wait times are calculated using the mps values given in
            # section 4.5 of the datasheet.  For example, 10 mps would enable
            # a periodic fetch 10 times every second. You then add the 
            # repeatability measurement time.
            if val == 4:
                self._periodic_wait = 0.1
            elif val == 3:
                self._periodic_wait = 0.25
            elif val == 2:
                self._periodic_wait = 0.5
            elif val == 1:
                self._periodic_wait = 1
            else:
                self._periodic_wait = 2

            self.__periodic_interval = val

    @property
    def periodic_fetch(self):
        curr = time.time()
        
        if self._periodic_next > curr:
            time.sleep(self._periodic_next - curr)

        self._write_block(PERIODIC_FETCH[0], [PERIODIC_FETCH[1]])
        block = self._read_block(SINGLE_MODE[self.clock_stretch][0], 6)

        self._periodic_next = time.time() + self._periodic_wait + \
            TIMING[self.repeatability]

        return self._process_data(block)

    @property
    def repeatability(self):
        return self.__repeatability

    @repeatability.setter
    def repeatability(self, val: int):
        if val >= 1 and val <= 3:
            self.__repeatability = val

    @property
    def clock_stretch(self):
        return self.__clock_stretch

    @clock_stretch.setter
    def clock_stretch(self, val: bool):
        self.__clock_stretch = int(val)

    @property
    def heater(self):
        return bool(self._status & 0x2000)

    @heater.setter
    def heater(self, val: bool):
        if val:
            self._write_block(HEATER_ON[0], [HEATER_ON[1]])
        else:
            self._write_block(HEATER_OFF[0], [HEATER_OFF[1]])

    @property
    def high_alert_set(self):
        return self._read_alert_data(ALERT_HIGH_RSET)

    @high_alert_set.setter
    def high_alert_set(self, val: tuple):
        self._write_alert_data(ALERT_HIGH_WSET, val)

    @property
    def high_alert_clear(self):
        return self._read_alert_data(ALERT_HIGH_RCLEAR)

    @high_alert_clear.setter
    def high_alert_clear(self, val: tuple):
        self._write_alert_data(ALERT_HIGH_WCLEAR, val)

    @property
    def low_alert_set(self):
        return self._read_alert_data(ALERT_LOW_RSET)

    @low_alert_set.setter
    def low_alert_set(self, val: tuple):
        self._write_alert_data(ALERT_LOW_WSET, val)

    @property
    def low_alert_clear(self):
        return self._read_alert_data(ALERT_LOW_RCLEAR)

    @low_alert_clear.setter
    def low_alert_clear(self, val: tuple):
        self._write_alert_data(ALERT_LOW_WCLEAR, val)

    # https://github.com/closedcube/ClosedCube_SHT31D_Arduino
    def _read_alert_data(self, cmd: tuple):
        self._write_block(cmd[0], [cmd[1]])
        b1, b2, crc = self._read_block(cmd[0], 3)

        if self.crc8((b1, b2)) != crc:
            return (None, None)

        data = self.merge_blocks(b1, b2)
        humd = data & 0xFE00
        temp = (data & 0x01FF) << 7

        return(self.to_fahrenheit(temp), self.to_relative(humd))

    def _write_alert_data(self, cmd: tuple, val: tuple):
        humd = self.from_relative(val[1])
        temp = self.from_fahrenheit(val[0])
        data = (humd & 0xFE00) | ((temp >> 7) & 0x01FF)

        b1 = data >> 8
        b2 = data & 0xFF
        crc = self.crc8([b1, b2])

        self._write_block(cmd[0], [cmd[1], b1, b2, crc])

    @property
    def is_crc_error(self):
        return bool(self._status & 0x0001)

    @property
    def is_command_error(self):
        return bool(self._status & 0x0002)

    @property
    def is_reset(self):
        return bool(self._status & 0x0010)

    @property
    def is_temperature_alert(self):
        return bool(self._status & 0x0400)

    @property
    def is_humidity_alert(self):
        return bool(self._status & 0x0800)

    @property
    def is_alert(self):
        return bool(self._status & 0x8000)

    @property
    def _status(self):
        self._write_block(STATUS[0], [STATUS[1]])
        status = self._read_block(0, 2)

        return self.merge_blocks(status[0], status[1])

    def reset(self):
        self._write_block(SOFT_RESET[0], [SOFT_RESET[1]])

    def clear_status(self):
        self._write_block(CLEAR_STATUS[0], [CLEAR_STATUS[1]])

    def _process_data(self, data: list):
        temp = None
        humd = None

        if self.crc8(data[0:2]) == data[2]:
            temp = self.merge_blocks(data[0], data[1])
            temp = self.to_fahrenheit(temp)

        if self.crc8(data[3:5]) == data[5]:
            humd = self.merge_blocks(data[3], data[4])
            humd = self.to_relative(humd)

        return (temp, humd)

    def _read_block(self, cmd, num: int=2):
        return self._bus.read_i2c_block_data(self._dev, cmd, num)

    def _write_block(self, cmd, vals: list):
        self._bus.write_i2c_block_data(self._dev, cmd, vals)
        time.sleep(TIMING[0])

    @staticmethod
    def merge_blocks(b1: int, b2: int):
        return b1 << 8 | b2

    @staticmethod
    def to_relative(humd: int):
        return 100.0 * (humd / 65535.0)

    @staticmethod
    def from_relative(humd: int):
        return int(humd / 100.0 * 65565.0)

    @staticmethod
    def to_fahrenheit(temp: int):
        return -49.0 + 315.0 * (temp / 65535.0)

    @staticmethod
    def from_fahrenheit(temp: int):
        return int((temp + 49.0) * 13107.0 / 63.0)

    @staticmethod
    def to_celsius(temp: int):
        return -45.0 + 175.0 * (temp / 65535.0)

    @staticmethod
    def from_celsius(temp: float):
        return int((temp + 45.0) * 13107.0 / 35.0)

    # https://github.com/ralf1070/Adafruit_Python_SHT31/
    @staticmethod
    def crc8(blocks):
        polynomial = 0x31
        crc = 0xFF
  
        index = 0
        for index in range(0, len(blocks)):
            crc ^= blocks[index]
            for i in range(8, 0, -1):
                if crc & 0x80:
                    crc = (crc << 1) ^ polynomial
                else:
                    crc = (crc << 1)

        return crc & 0xFF
        