#include "fla5000.h"
#include <libusb-1.0/libusb.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
struct fla5000 { libusb_context *ctx; libusb_device_handle *usb; fla5000_info info; unsigned integration_parameter; };
static int exact(fla5000*d,unsigned char ep,unsigned char*b,int size,unsigned timeout){
 int done=0;int r=libusb_bulk_transfer(d->usb,ep,b,size,&done,timeout);
 if(r)return r;
 return done==size?0:LIBUSB_ERROR_IO;
}
static int read_memory(fla5000*d,unsigned a,unsigned char*b,unsigned n){
 unsigned char cmd[]={6,a&255,(a>>8)&255,n&255,(n>>8)&255};
 int r=exact(d,2,cmd,5,1000);return r?r:exact(d,0x88,b,(int)n,1000);
}
static float float_le(const unsigned char*b){
 uint32_t u=(uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);float f;memcpy(&f,&u,4);return f;
}
static int read_info(fla5000*d){
 int r=read_memory(d,0x10,(unsigned char*)d->info.model,16);if(r)return r;
 r=read_memory(d,0x20,(unsigned char*)d->info.serial,16);if(r)return r;
 r=read_memory(d,0x30,(unsigned char*)d->info.firmware,16);if(r)return r;
 /* This implementation is validated for this legacy firmware only. */
 if(strcmp(d->info.model,"FLA5000")||strcmp(d->info.firmware,"VER7.1"))return LIBUSB_ERROR_NOT_SUPPORTED;
 unsigned char count=0;r=read_memory(d,0x100,&count,1);if(r)return r;
 if(!count||count>FLA5000_MAX_ANCHORS)return LIBUSB_ERROR_IO;
 d->info.anchor_count=count;
 for(unsigned i=0;i<count;i++){
  unsigned char b[8];r=read_memory(d,0x104+i*8,b,8);if(r)return r;
  d->info.anchors[i].wavelength_nm=float_le(b);d->info.anchors[i].pixel=float_le(b+4);
 }
 return 0;
}
/* Discovery only: never open/claim the device or send a sampling command. */
int fla5000_device_present(void){
 libusb_context*ctx=NULL;int result=libusb_init(&ctx);if(result)return result;
 libusb_device**list=NULL;ssize_t n=libusb_get_device_list(ctx,&list);
 if(n<0){libusb_exit(ctx);return (int)n;}
 result=0;
 for(ssize_t i=0;i<n;i++){
  struct libusb_device_descriptor desc;if(libusb_get_device_descriptor(list[i],&desc))continue;
  if(desc.idVendor==0xf0d0&&desc.idProduct==0x5001){result=1;break;}
 }
 libusb_free_device_list(list,1);libusb_exit(ctx);return result;
}
int fla5000_open(fla5000**out,const char*serial){
 if(!out)return LIBUSB_ERROR_INVALID_PARAM;
 *out=NULL;
 fla5000*d=calloc(1,sizeof(*d));if(!d)return LIBUSB_ERROR_NO_MEM;
 int r=libusb_init(&d->ctx);if(r){free(d);return r;}
 libusb_device**list=NULL;ssize_t n=libusb_get_device_list(d->ctx,&list);if(n<0){r=(int)n;goto end;}
 r=LIBUSB_ERROR_NO_DEVICE;
 for(ssize_t i=0;i<n;i++){
  struct libusb_device_descriptor desc;if(libusb_get_device_descriptor(list[i],&desc))continue;
  if(desc.idVendor!=0xf0d0||desc.idProduct!=0x5001)continue;
  r=libusb_open(list[i],&d->usb);if(r)continue;
  r=libusb_claim_interface(d->usb,0);if(r){libusb_close(d->usb);d->usb=NULL;continue;}
  memset(&d->info,0,sizeof(d->info));r=read_info(d);
  if(!r&&serial&&strcmp(serial,d->info.serial))r=LIBUSB_ERROR_NO_DEVICE;
  if(!r)break;
  libusb_release_interface(d->usb,0);libusb_close(d->usb);d->usb=NULL;
 }
 libusb_free_device_list(list,1);
end:
 if(r){fla5000_close(d);return r;}*out=d;return 0;
}
void fla5000_close(fla5000*d){if(!d)return;if(d->usb){libusb_release_interface(d->usb,0);libusb_close(d->usb);}if(d->ctx)libusb_exit(d->ctx);free(d);}
/* Check the original device identity, without sending a firmware command.
 * An unplugged handle must not become valid just because another unit appears. */
int fla5000_check_connected(fla5000*d){
 if(!d||!d->usb)return LIBUSB_ERROR_NO_DEVICE;
 libusb_device**list=NULL;ssize_t n=libusb_get_device_list(d->ctx,&list);
 if(n<0)return (int)n;
 libusb_device*original=libusb_get_device(d->usb);
 int result=LIBUSB_ERROR_NO_DEVICE;
 for(ssize_t i=0;i<n;i++)if(list[i]==original){result=0;break;}
 libusb_free_device_list(list,1);
 return result;
}
const fla5000_info*fla5000_get_info(const fla5000*d){return d?&d->info:NULL;}
const char*fla5000_error_name(int r){return libusb_error_name(r);}

int fla5000_set_integration_parameter(fla5000*d,unsigned ms){
 if(!d || ms<1 || ms>65535)return LIBUSB_ERROR_INVALID_PARAM;
 d->integration_parameter=0;
 unsigned char cmd[]={2,ms&255,(ms>>8)&255},ack=0;
 int r=exact(d,2,cmd,3,1000);
 if(!r)r=exact(d,0x88,&ack,1,1000);
 if(!r && ack!=1)r=LIBUSB_ERROR_IO;
 if(!r)d->integration_parameter=ms;
 return r;
}
int fla5000_decode(const unsigned char*wire,size_t len,uint16_t*pixels){
 if(!wire||!pixels||len!=FLA5000_PIXELS*2)return LIBUSB_ERROR_INVALID_PARAM;
 for(unsigned i=0;i<FLA5000_PIXELS;i++){
  unsigned j=2*(FLA5000_PIXELS-1-i);
  pixels[i]=(uint16_t)(((unsigned)wire[j]<<8)|wire[j+1]);
 }
 return 0;
}
int fla5000_capture(fla5000*d,uint16_t pixels[FLA5000_PIXELS]){
 if(!d||!pixels||!d->integration_parameter)return LIBUSB_ERROR_INVALID_PARAM;
 unsigned char cmd[]={1,0},wire[FLA5000_PIXELS*2];
 int r=exact(d,2,cmd,2,1000);
 if(!r)r=exact(d,0x86,wire,sizeof(wire),2000+(d->integration_parameter+39)/40);
 if(r){d->integration_parameter=0;return r;}
 return fla5000_decode(wire,sizeof(wire),pixels);
}
