#ifndef FLA5000_H
#define FLA5000_H
#include <stdint.h>
#include <stddef.h>
#define FLA5000_PIXELS 2048
#define FLA5000_MAX_ANCHORS 32
/* One context per device; calls on a context must be serialized. */
typedef struct fla5000 fla5000;
typedef struct { float wavelength_nm; float pixel; } fla5000_anchor;
typedef struct {
 char model[17], serial[17], firmware[17];
 unsigned anchor_count;
 fla5000_anchor anchors[FLA5000_MAX_ANCHORS];
} fla5000_info;
/* Errors are negative libusb codes. No firmware/EEPROM writes are exposed. */
int fla5000_open(fla5000 **out, const char *serial);
void fla5000_close(fla5000 *dev);
const fla5000_info *fla5000_get_info(const fla5000 *dev);
/* Legacy integer parameter, 1..1000. Physical exposure units unverified. */
int fla5000_set_integration_parameter(fla5000 *dev, unsigned ms);
/* Raw ADC words in ascending SDK pixel order. Intensity = 32767 - ADC.
 * Call set_integration first. On transfer failure close/reopen device. */
int fla5000_capture(fla5000 *dev, uint16_t pixels[FLA5000_PIXELS]);
/* Offline frame decoder, preserves all raw edge pixels. */
int fla5000_decode(const unsigned char *wire, size_t len, uint16_t *pixels);
const char *fla5000_error_name(int code);
#endif
