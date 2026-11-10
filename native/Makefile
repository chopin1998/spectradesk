CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -fPIC
all: libfla5000.so
libfla5000.so: fla5000.c processing.c calibration.c fla5000.h processing.h calibration.h
	$(CC) $(CFLAGS) -shared -o $@ fla5000.c processing.c calibration.c $$(pkg-config --cflags --libs libusb-1.0) -lm
clean:
	rm -f libfla5000.so
.PHONY: all clean
