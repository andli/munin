#ifndef MUNIN_DEBUG_H
#define MUNIN_DEBUG_H

/* Central debug logging toggle. Define MUNIN_DEBUG (e.g. via CFLAGS or here) to enable verbose logs. */
#ifndef MUNIN_DEBUG
#define MUNIN_DEBUG 0
#endif

#if MUNIN_DEBUG
#include <zephyr/sys/printk.h>
#define MLOG(fmt, ...) printk("[DBG] " fmt, ##__VA_ARGS__)
#else
#define MLOG(fmt, ...) do { } while (0)
#endif

#endif /* MUNIN_DEBUG_H */
