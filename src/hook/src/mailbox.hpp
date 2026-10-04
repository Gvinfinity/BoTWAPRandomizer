#pragma once
#include <cstdint>

#define MAILBOX_MAGIC_1 0x41504D42 // "APMB"
#define MAILBOX_MAGIC_2 0x424F5457 // "BOTW"

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
    uint32_t magic_1;
    uint32_t magic_2;
    uint32_t status;       // 0=NotReady, 1=MainMenu, 2=InGame, 3=Paused
    uint32_t in_head;
    uint32_t in_tail;
    uint32_t out_head;
    uint32_t out_tail;
    uint32_t tick_count;   // Incremented every hook tick for liveness monitoring

    IncomingItem incoming_queue[256];
    OutgoingCheck outgoing_queue[256];

    // Debug area (starts at mailbox base + 0x3020)
    char debug_msg[64];    
};
