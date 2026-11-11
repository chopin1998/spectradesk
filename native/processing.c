#include "processing.h"
#include <libusb-1.0/libusb.h>
#include <math.h>
#include <string.h>
int fla5000_sta_ms_parameter(double ms, unsigned *parameter) {
    if (!parameter || !isfinite(ms) || ms < 1.0 || ms > 20.0)
        return LIBUSB_ERROR_INVALID_PARAM;
    *parameter = (unsigned)(ms * 50.0);
    return 0;
}
int fla5000_smooth(const float *input, float *output, unsigned radius) {
    if (!input || !output || radius > 250) return LIBUSB_ERROR_INVALID_PARAM;
    float tmp[FLA5000_PIXELS];
    double sum = 0;
    unsigned left = 0, right = 0;
    for (unsigned i = 0; i < FLA5000_PIXELS; ++i) {
        unsigned lo = i > radius ? i - radius : 0;
        unsigned hi = i + radius + 1;
        if (hi > FLA5000_PIXELS) hi = FLA5000_PIXELS;
        while (right < hi) sum += input[right++];
        while (left < lo) sum -= input[left++];
        tmp[i] = (float)(sum / (hi - lo));
    }
    memcpy(output, tmp, sizeof(tmp));
    return 0;
}
int fla5000_measure(fla5000 *dev, unsigned average, unsigned radius,
                    float mean[FLA5000_PIXELS], float processed[FLA5000_PIXELS]) {
    if (!dev || !mean || !processed || mean == processed ||
        average < 1 || average > 1000 || radius > 250)
        return LIBUSB_ERROR_INVALID_PARAM;
    double sum[FLA5000_PIXELS] = {0};
    uint16_t raw[FLA5000_PIXELS];
    for (unsigned frame = 0; frame < average; ++frame) {
        int r = fla5000_capture(dev, raw);
        if (r) return r; /* Do not return a partial average as a complete one. */
        for (unsigned i = 0; i < FLA5000_PIXELS; ++i)
            sum[i] += 32767 - (int)raw[i];
    }
    for (unsigned i = 0; i < FLA5000_PIXELS; ++i)
        mean[i] = (float)(sum[i] / average);
    return fla5000_smooth(mean, processed, radius);
}
int fla5000_auto(fla5000 *dev, unsigned start, float target,
                 fla5000_auto_result *result) {
    if (!dev || !result || start < 15 || start > 65535 ||
        !isfinite(target) || target < 4000 || target > 14000)
        return LIBUSB_ERROR_INVALID_PARAM;
    memset(result, 0, sizeof(*result));
    unsigned parameter = start > 30000 ? 30000 : start;
    for (unsigned step = 0; step < 16; ++step) {
        int r = fla5000_set_integration_parameter(dev, parameter);
        if (r) return r;
        result->parameter = parameter;
        result->iterations = step + 1;
        float mean[FLA5000_PIXELS], processed[FLA5000_PIXELS];
        r = fla5000_measure(dev, 3, 0, mean, processed);
        if (r) return r;
        float peak = mean[10];
        for (unsigned i = 11; i <= 2040; ++i)
            if (mean[i] > peak) peak = mean[i];
        result->peak = peak;
        if (fabsf(peak - target) <= target * 0.08f) {
            result->status = 0;
            return 0;
        }
        float baseline = 0;
        for (unsigned i = 10; i < 70; ++i) baseline += mean[i];
        baseline /= 60;
        double ratio = (target - baseline) / fmax(peak - baseline, 1.0);
        /* Clipped frames cannot estimate the real peak: back off decisively. */
        if (peak >= 16500) ratio = 0.5;
        if (ratio < 0.5) ratio = 0.5;
        if (ratio > 2.0) ratio = 2.0;
        unsigned next = (unsigned)floor(parameter * ratio + 0.5);
        if (next < 15) next = 15;
        if (next > 30000) next = 30000;
        if (next == parameter) {
            result->status = parameter == 15 ? 1 : (parameter == 30000 ? 2 : 3);
            return 0;
        }
        parameter = next;
    }
    result->status = 3;
    return 0;
}
