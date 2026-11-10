#ifndef FLA_PROCESSING_H
#define FLA_PROCESSING_H
#include "fla5000.h"
/* Average N physical frames. Preserve the mean separately from smoothing. */
int fla5000_measure(fla5000 *dev, unsigned average, unsigned smooth_radius,
                    float mean[FLA5000_PIXELS], float processed[FLA5000_PIXELS]);
/* Host box smoothing: centered 2*radius+1 pixels, truncated at edges.
 * radius 0 disables smoothing. Not asserted bit-identical to STA's filter. */
int fla5000_smooth(const float *input, float *output, unsigned radius);
/* STA optional legacy conversion, not a metrological exposure calibration. */
int fla5000_sta_ms_parameter(double nominal_ms, unsigned *parameter);
typedef struct {
 unsigned parameter, iterations;
 float peak;
 /* 0=target reached, 1=lower bound, 2=upper bound, 3=iteration limit */
 int status;
} fla5000_auto_result;
/* Bounded host feedback, based on unsmoothed peak; observed profile ceiling. */
int fla5000_auto(fla5000 *dev, unsigned start, float target,
                 fla5000_auto_result *result);
#endif
