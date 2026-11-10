#include "calibration.h"
#include <libusb-1.0/libusb.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
int fla5000_wavelengths(const fla5000_info *info, float *nm, uint8_t *extrapolated) {
    if (!info || !nm || !extrapolated || info->anchor_count < 2 ||
        info->anchor_count > FLA5000_MAX_ANCHORS) return LIBUSB_ERROR_INVALID_PARAM;
    unsigned n = info->anchor_count;
    for (unsigned i = 0; i < n; ++i) {
        const fla5000_anchor *a = &info->anchors[i];
        if (!isfinite(a->pixel) || !isfinite(a->wavelength_nm) ||
            a->pixel < 0 || a->pixel > 2047 || a->wavelength_nm <= 0 ||
            (i && (a->pixel <= info->anchors[i-1].pixel ||
                   a->wavelength_nm <= info->anchors[i-1].wavelength_nm)))
            return LIBUSB_ERROR_INVALID_PARAM;
    }
    unsigned j = 0;
    for (unsigned p = 0; p < FLA5000_PIXELS; ++p) {
        while (j + 2 < n && p >= info->anchors[j+1].pixel) ++j;
        const fla5000_anchor *a = &info->anchors[j], *b = &info->anchors[j+1];
        double slope = ((double)b->wavelength_nm-a->wavelength_nm)/(b->pixel-a->pixel);
        nm[p] = (float)(a->wavelength_nm + ((double)p-a->pixel)*slope);
        extrapolated[p] = p < info->anchors[0].pixel || p > info->anchors[n-1].pixel;
    }
    return 0;
}
int fla5000_smooth_sta(const float *input, float *output, size_t length, unsigned count) {
    if (!input || !output || !length || length > FLA5000_PIXELS ||
        count > 250 || (count && length <= 2*count)) return LIBUSB_ERROR_INVALID_PARAM;
    if (!count) {memmove(output, input, length*sizeof(float)); return 0;}
    float tmp[FLA5000_PIXELS];
    for (size_t i=0; i<count; ++i) tmp[i]=input[count];
    for (size_t i=count; i<length-count; ++i) {
        float sum=0;
        /* Sequential float summation reproduces the SDK's rounding order. */
        for (size_t j=i-count; j<i+count; ++j) sum+=input[j];
        tmp[i]=sum/(2*count);
    }
    for (size_t i=length-count; i<length; ++i) tmp[i]=input[length-count];
    memcpy(output,tmp,length*sizeof(float));
    return 0;
}
