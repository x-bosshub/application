import RPi.GPIO as GPIO
import time

class TM1637:
    """
    Driver for the TM1637 4-digit 7-segment display.
    Adapted from micropython-tm1637 by mcauser
    Updated to support decimal points and floating point numbers.
    """
    DIO_PIN = None
    CLK_PIN = None

    # Segment mapping for digits 0-9, '-', space, E, r, and A-Z characters
    _SEGMENTS = {
        '0': 0x3F, '1': 0x06, '2': 0x5B, '3': 0x4F,
        '4': 0x66, '5': 0x6D, '6': 0x7D, '7': 0x07,
        '8': 0x7F, '9': 0x6F, '-': 0x40, ' ': 0x00,
        'A': 0x77, 'B': 0x7C, 'C': 0x39, 'D': 0x5E,
        'E': 0x79, 'F': 0x71, 'G': 0x3D, 'H': 0x76,
        'I': 0x06, 'J': 0x1E, 'L': 0x38, 'N': 0x54,
        'O': 0x3F, 'P': 0x73, 'Q': 0x6B, 'R': 0x50,
        'S': 0x6D, 'T': 0x78, 'U': 0x3E, 'Y': 0x6E,
        'r': 0x50, 'Z': 0x5B
    }
    def __init__(self, clk_pin, dio_pin, brightness=7):
        self.CLK_PIN = clk_pin
        self.DIO_PIN = dio_pin
        self.brightness = min(brightness, 7)  # 0-7

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)  # Use BCM numbering for GPIO pins
        GPIO.setup(self.CLK_PIN, GPIO.OUT)
        GPIO.setup(self.DIO_PIN, GPIO.OUT)

        self.clear()
        self.set_brightness(self.brightness)

    def _start(self):
        GPIO.output(self.DIO_PIN, GPIO.HIGH)
        GPIO.output(self.CLK_PIN, GPIO.HIGH)
        GPIO.output(self.DIO_PIN, GPIO.LOW)

    def _stop(self):
        GPIO.output(self.CLK_PIN, GPIO.LOW)
        GPIO.output(self.DIO_PIN, GPIO.LOW)
        GPIO.output(self.CLK_PIN, GPIO.HIGH)
        GPIO.output(self.DIO_PIN, GPIO.HIGH)

    def _write_byte(self, data):
        for i in range(8):
            GPIO.output(self.CLK_PIN, GPIO.LOW)
            if data & 0x01:
                GPIO.output(self.DIO_PIN, GPIO.HIGH)
            else:
                GPIO.output(self.DIO_PIN, GPIO.LOW)
            data >>= 1
            GPIO.output(self.CLK_PIN, GPIO.HIGH)
        
        # Wait for ACK
        GPIO.output(self.CLK_PIN, GPIO.LOW)
        GPIO.setup(self.DIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        time.sleep(0.000001)
        ack = GPIO.input(self.DIO_PIN) == GPIO.LOW
        GPIO.setup(self.DIO_PIN, GPIO.OUT)
        GPIO.output(self.CLK_PIN, GPIO.HIGH)
        return ack

    def set_brightness(self, brightness):
        """Set the brightness of the display (0-7)."""
        self.brightness = min(brightness, 7)
        self._write_command(0x88 + self.brightness)

    def _write_command(self, cmd):
        self._start()
        self._write_byte(cmd)
        self._stop()

    def _display_data(self, data):
        self._write_command(0x40)  # Data command
        self._start()
        self._write_byte(0xC0)  # Address command (start from 0)
        for digit_data in data:
            self._write_byte(digit_data)
        self._stop()
        self._write_command(0x88 + self.brightness)  # Display control

    def write(self, segments, colon=False):
        """
        Write raw segments to the display.
        segments is a list of 4 bytes, one for each digit.
        """
        display_segments = list(segments)
        if colon:
            # The colon on most modules is the DP of the 2nd digit
            display_segments[1] |= 0x80  
        self._display_data(display_segments)

    def show(self, string, colon=False):
        """
        Display a string of up to 4 characters.
        Handles digits 0-9, '-', and decimal points.
        The decimal point does not occupy a digit position but is attached
        to the previous character. The string is right-aligned.
        """
        s = str(string).strip()
        segments = [0x00] * 4
        display_pos = 3  # Start filling from the rightmost digit
        dot_pending = False

        for char in reversed(s):
            if display_pos < 0:
                break
            
            if char == '.':
                dot_pending = True
                continue
            
            segment = self._SEGMENTS.get(char, 0x00) # Get segment data, default to blank
            
            if dot_pending:
                segment |= 0x80  # Set the decimal point bit
                dot_pending = False
            
            segments[display_pos] = segment
            display_pos -= 1
        
        self.write(segments, colon)

    def show_number(self, num, colon=False):
        """
        Display an integer or float number.
        Automatically formats the number to fit the 4-digit display.
        Shows 'Err' if the number is too large to display.
        """
        if not isinstance(num, (int, float)):
             self.show("None")
             return

        # Format the number to a string
        if isinstance(num, float):
            if abs(num) >= 1000:
                s = str(int(round(num, 0))) # e.g., 1234.5 -> 1235
            elif abs(num) >= 100:
                s = "{:.1f}".format(num)    # e.g., 123.45 -> 123.5
            elif abs(num) >= 10:
                s = "{:.2f}".format(num)    # e.g., 12.345 -> 12.35
            else:
                s = "{:.2f}".format(num)    # e.g., 1.2345 -> 1.235
        else: # int
            s = str(num)

        # Check if the formatted number can be displayed
        # Count digits only, excluding '-' and '.'
        digit_count = len([c for c in s if c.isdigit()])
        if digit_count > 4:
            self.show("----")
            return
            
        self.show(s, colon)

    def clear(self):
        """Clear the display."""
        self.write([0, 0, 0, 0])

    def cleanup(self):
        """Clean up GPIO settings when done."""
        self.clear()
        GPIO.cleanup()