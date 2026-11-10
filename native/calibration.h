#ifndef FLA_CALIBRATION_H
#define FLA_CALIBRATION_H
#include "fla5000.h"
/* SDK-compatible piecewise linear mapping; end segments extrapolate.
 * extrapolated[p]=1 outside the span of measured calibration anchors. */
int fla5000_wavelengths(const fla5000_info *info, float *nm, uint8_t *extrapolated);
/* Legacy SDK kernel: 2*N points [i-N,i+N), original-value edge extension.
 * N=0 bypasses processing. Count 1..250; length must exceed 2*N. */
int fla5000_smooth_sta(const float *input, float *output, size_t length, unsigned count);
#endif
