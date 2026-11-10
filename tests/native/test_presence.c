#include <assert.h>
#include <stdint.h>
#include <libusb-1.0/libusb.h>

static libusb_device *original=(libusb_device *)(uintptr_t)1;
static libusb_device *other=(libusb_device *)(uintptr_t)2;
static libusb_device *devices[3];
static ssize_t count;
static int freed;
static ssize_t fake_list(libusb_context *ctx,libusb_device ***list){
 (void)ctx;*list=devices;return count;
}
static libusb_device *fake_device(libusb_device_handle *handle){
 (void)handle;return original;
}
static void fake_free(libusb_device **list,int unref){
 assert(list==devices);assert(unref==1);freed++;
}
static int fake_init(libusb_context **ctx){*ctx=(libusb_context *)(uintptr_t)1;return 0;}
static void fake_exit(libusb_context *ctx){assert(ctx==(libusb_context *)(uintptr_t)1);}
static int fake_descriptor(libusb_device *dev,struct libusb_device_descriptor *desc){
 *desc=(struct libusb_device_descriptor){0};
 if(dev==original){desc->idVendor=0xf0d0;desc->idProduct=0x5001;}
 return 0;
}
#define libusb_init fake_init
#define libusb_exit fake_exit
#define libusb_get_device_descriptor fake_descriptor
#define libusb_get_device_list fake_list
#define libusb_get_device fake_device
#define libusb_free_device_list fake_free
#include "../../native/fla5000.c"

int main(void){
 struct fla5000 dev={.ctx=(libusb_context *)(uintptr_t)1,.usb=(libusb_device_handle *)(uintptr_t)1};
 assert(fla5000_check_connected(NULL)==LIBUSB_ERROR_NO_DEVICE);
 devices[0]=other;devices[1]=original;count=2;
 assert(fla5000_check_connected(&dev)==0);
 assert(freed==1);
 /* A remaining/replugged unit is not the original open handle. */
 devices[0]=other;count=1;
 assert(fla5000_check_connected(&dev)==LIBUSB_ERROR_NO_DEVICE);
 assert(freed==2);
 count=0;
 assert(fla5000_check_connected(&dev)==LIBUSB_ERROR_NO_DEVICE);
 assert(freed==3);
 count=LIBUSB_ERROR_IO;
 assert(fla5000_check_connected(&dev)==LIBUSB_ERROR_IO);
 assert(freed==3);
 count=0;
 assert(fla5000_device_present()==0);
 devices[0]=other;count=1;
 assert(fla5000_device_present()==0);
 devices[1]=original;count=2;
 assert(fla5000_device_present()==1);
 count=LIBUSB_ERROR_IO;
 assert(fla5000_device_present()==LIBUSB_ERROR_IO);
 return 0;
}
