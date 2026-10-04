#include "mailbox.hpp"
#include <iostream>
#include <cstring>

namespace ksys {
    namespace act {
        using acquireItem_t = void(*)(void* actorSystem, const char* actorName, int count);
        inline acquireItem_t acquireItem = reinterpret_cast<acquireItem_t>(0x03741B20);

        inline void* getSystem() {
            return *reinterpret_cast<void**>(0x105B8C00);
        }
    }
}

Mailbox* g_mailbox = reinterpret_cast<Mailbox*>(0x11000000);

// Global flag to prevent infinite loops when we give items and trigger the pickup hook
bool g_isInjecting = false; 

extern "C" void AP_Process_Mailbox() {
    if (!g_mailbox || g_mailbox->magic != MAILBOX_MAGIC) return; 

    // PROCESS INCOMING ITEMS (Receive)
    while (g_mailbox->in_tail < g_mailbox->in_head) {
        uint32_t index = g_mailbox->in_tail % 256;
        IncomingItem& item = g_mailbox->incoming_queue[index];

        void* actSys = ksys::act::getSystem();
        if (actSys) {
            g_isInjecting = true; // Prevent outgoing trigger
            ksys::act::acquireItem(actSys, item.actorName, item.quantity);
            g_isInjecting = false;
        }

        g_mailbox->in_tail++;
    }
}

// Intercepts natural item pickups (r3=actorSystem, r4=actorName, r5=count)
extern "C" void AP_Process_Outgoing_Test(void* actorSystem, const char* actorName, int count) {
    if (!g_mailbox || g_mailbox->magic != MAILBOX_MAGIC || g_isInjecting) return;

    // PROCESS OUTGOING CHECK (Chest Open)
    // For this test, whenever Link naturally picks up a "Weapon_" or "Item_",
    // we intercept it and dispatch a mock Location ID to the mailbox.
    if (std::strncmp(actorName, "Weapon_", 7) == 0 || std::strncmp(actorName, "Item_", 5) == 0) {
        
        uint32_t index = g_mailbox->out_head % 256;
        OutgoingCheck& check = g_mailbox->outgoing_queue[index];
        check.seqId = g_mailbox->out_head;
        check.apLocationId = 0x5000 + (g_mailbox->out_head); // Mock Location ID
        check.isShop = 0;
        
        g_mailbox->out_head++;
    }
}
