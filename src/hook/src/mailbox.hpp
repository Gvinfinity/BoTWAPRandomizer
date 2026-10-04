#pragma once
#include <cstdint>

#define MAILBOX_MAGIC 0x424F5457 // "BOTW"

struct IncomingItem {
    uint32_t seqId;
    uint32_t apItemId;
    char actorName[16];
    uint32_t quantity;
    uint32_t flags;
};

struct OutgoingCheck {
    uint32_t seqId;
    uint64_t apLocationId;
    uint32_t isShop;
};

struct Mailbox {
    uint32_t magic;
    uint32_t version;
    uint32_t status;
    uint32_t in_head;
    uint32_t in_tail;
    uint32_t out_head;
    uint32_t out_tail;
    uint32_t padding;

    IncomingItem incoming_queue[256];
    OutgoingCheck outgoing_queue[256];
};
