# Build ze0_cov.c as an out-of-tree TCG plugin for the pinned QEMU.
#
# Usage:
#   make QEMU_SRC=/path/to/qemu-11.1.3 QEMU_BUILD=/path/to/build
#
# The plugin API header and the GLib flags come from the pinned source tree;
# nothing is copied into the repository. The .so lands next to this Makefile.
QEMU_SRC ?= $(HOME)/.cache/qemu-ze0/qemu-11.1.3
QEMU_BUILD ?= $(HOME)/.cache/qemu-ze0/build

CC ?= cc
PKG_CONFIG ?= pkg-config

PLUGIN = libze0_cov.so
CFLAGS += -std=gnu11 -O2 -fPIC -Wall -Wextra \
	-I$(QEMU_SRC)/include/plugins
CFLAGS += $(shell $(PKG_CONFIG) --cflags glib-2.0 2>/dev/null)
LDFLAGS += -shared
LDFLAGS += $(shell $(PKG_CONFIG) --libs glib-2.0 2>/dev/null)

.PHONY: all clean
all: $(PLUGIN)

$(PLUGIN): ze0_cov.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f $(PLUGIN)
