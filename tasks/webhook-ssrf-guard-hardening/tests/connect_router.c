#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

struct peer_entry {
    int descriptor;
    struct sockaddr_storage address;
    socklen_t length;
    struct peer_entry *next;
};

static pthread_mutex_t peer_lock = PTHREAD_MUTEX_INITIALIZER;
static struct peer_entry *peers;
static int (*system_connect)(int, const struct sockaddr *, socklen_t);
static int (*system_getpeername)(int, struct sockaddr *, socklen_t *);
static int (*system_close)(int);
static pthread_once_t initialized = PTHREAD_ONCE_INIT;

static void initialize(void) {
    system_connect = dlsym(RTLD_NEXT, "connect");
    system_getpeername = dlsym(RTLD_NEXT, "getpeername");
    system_close = dlsym(RTLD_NEXT, "close");
}

static void forget_peer(int descriptor) {
    struct peer_entry **cursor = &peers;
    while (*cursor) {
        if ((*cursor)->descriptor == descriptor) {
            struct peer_entry *removed = *cursor;
            *cursor = removed->next;
            free(removed);
            return;
        }
        cursor = &(*cursor)->next;
    }
}

static int address_text(const struct sockaddr *address, char *text, unsigned *port) {
    if (address->sa_family == AF_INET) {
        const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
        *port = ntohs(ipv4->sin_port);
        return inet_ntop(AF_INET, &ipv4->sin_addr, text, INET6_ADDRSTRLEN) != NULL;
    }
    if (address->sa_family == AF_INET6) {
        const struct sockaddr_in6 *ipv6 = (const struct sockaddr_in6 *)address;
        *port = ntohs(ipv6->sin6_port);
        return inet_ntop(AF_INET6, &ipv6->sin6_addr, text, INET6_ADDRSTRLEN) != NULL;
    }
    return 0;
}

static int is_local(const struct sockaddr *address) {
    if (address->sa_family == AF_INET) {
        const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
        return (ntohl(ipv4->sin_addr.s_addr) >> 24) == 127;
    }
    if (address->sa_family == AF_INET6) {
        const struct sockaddr_in6 *ipv6 = (const struct sockaddr_in6 *)address;
        return IN6_IS_ADDR_LOOPBACK(&ipv6->sin6_addr) ||
            (IN6_IS_ADDR_V4MAPPED(&ipv6->sin6_addr) && ipv6->sin6_addr.s6_addr[12] == 127);
    }
    return 0;
}

static void record_attempt(const char *host, unsigned port, int prevented) {
    const char *channel = getenv("WEBHOOK_AUDIT_PATH");
    if (!channel) return;
    char message[256];
    int length = snprintf(message, sizeof(message),
        "{\"address\":\"%s\",\"port\":%u,\"prevented\":%s}\n",
        host, port, prevented ? "true" : "false");
    int descriptor = open(channel, O_WRONLY | O_NONBLOCK);
    if (descriptor >= 0) {
        if (length > 0 && length < (int)sizeof(message))
            write(descriptor, message, (size_t)length);
        close(descriptor);
    }
}

int connect(int descriptor, const struct sockaddr *address, socklen_t length) {
    pthread_once(&initialized, initialize);
    if (address && length >= sizeof(sa_family_t) && address->sa_family == AF_UNIX)
        return system_connect(descriptor, address, length);
    char host[INET6_ADDRSTRLEN];
    unsigned port = 0;
    if (!address || length < sizeof(sa_family_t) ||
        !address_text(address, host, &port)) {
        record_attempt("unsupported", 0, 1);
        errno = EACCES;
        return -1;
    }
    struct sockaddr_storage routed;
    memset(&routed, 0, sizeof(routed));
    int found = 0;
    const char *filename = getenv("WEBHOOK_ROUTE_FILE");
    FILE *routes = filename ? fopen(filename, "r") : NULL;
    if (routes) {
        char alias[INET6_ADDRSTRLEN], target[INET6_ADDRSTRLEN];
        unsigned alias_port, target_port;
        char line[256];
        while (fgets(line, sizeof(line), routes)) {
            int send_buffer = 0;
            if (sscanf(line, "%45s %u %45s %u %d", alias, &alias_port, target, &target_port, &send_buffer) < 4)
                continue;
            unsigned char alias_bytes[16];
            const void *original_bytes = address->sa_family == AF_INET
                ? (const void *)&((const struct sockaddr_in *)address)->sin_addr
                : (const void *)&((const struct sockaddr_in6 *)address)->sin6_addr;
            size_t address_bytes = address->sa_family == AF_INET ? 4 : 16;
            if (alias_port != port || inet_pton(address->sa_family, alias, alias_bytes) != 1 ||
                memcmp(alias_bytes, original_bytes, address_bytes) != 0) continue;
            if (address->sa_family == AF_INET) {
                struct sockaddr_in *ipv4 = (struct sockaddr_in *)&routed;
                ipv4->sin_family = AF_INET;
                ipv4->sin_port = htons(target_port);
                found = inet_pton(AF_INET, target, &ipv4->sin_addr) == 1;
            } else {
                struct sockaddr_in6 *ipv6 = (struct sockaddr_in6 *)&routed;
                ipv6->sin6_family = AF_INET6;
                ipv6->sin6_port = htons(target_port);
                found = inet_pton(AF_INET6, target, &ipv6->sin6_addr) == 1;
            }
            if (!is_local((const struct sockaddr *)&routed)) found = 0;
            if (found && send_buffer > 0)
                setsockopt(descriptor, SOL_SOCKET, SO_SNDBUF, &send_buffer, sizeof(send_buffer));
            break;
        }
        fclose(routes);
    }
    int permitted = found || is_local(address);
    record_attempt(host, port, !permitted);
    if (!permitted) {
        errno = EACCES;
        return -1;
    }
    pthread_mutex_lock(&peer_lock);
    forget_peer(descriptor);
    pthread_mutex_unlock(&peer_lock);
    socklen_t routed_length = address->sa_family == AF_INET ? sizeof(struct sockaddr_in) : sizeof(struct sockaddr_in6);
    int result = system_connect(descriptor, found ? (const struct sockaddr *)&routed : address, found ? routed_length : length);
    int saved_errno = errno;
    if (found && (result == 0 || saved_errno == EINPROGRESS || saved_errno == EWOULDBLOCK)) {
        struct peer_entry *entry = calloc(1, sizeof(*entry));
        if (entry) {
            entry->descriptor = descriptor;
            entry->length = length < sizeof(entry->address) ? length : sizeof(entry->address);
            memcpy(&entry->address, address, entry->length);
            pthread_mutex_lock(&peer_lock);
            entry->next = peers;
            peers = entry;
            pthread_mutex_unlock(&peer_lock);
        }
    }
    errno = saved_errno;
    return result;
}

int getpeername(int descriptor, struct sockaddr *address, socklen_t *length) {
    pthread_once(&initialized, initialize);
    socklen_t capacity = length ? *length : 0;
    int result = system_getpeername(descriptor, address, length);
    if (result != 0 || !address || !length) return result;
    pthread_mutex_lock(&peer_lock);
    for (struct peer_entry *entry = peers; entry; entry = entry->next) {
        if (entry->descriptor != descriptor) continue;
        memcpy(address, &entry->address, capacity < entry->length ? capacity : entry->length);
        *length = entry->length;
        break;
    }
    pthread_mutex_unlock(&peer_lock);
    return result;
}

int close(int descriptor) {
    pthread_once(&initialized, initialize);
    pthread_mutex_lock(&peer_lock);
    forget_peer(descriptor);
    pthread_mutex_unlock(&peer_lock);
    return system_close(descriptor);
}
