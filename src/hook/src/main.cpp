#include "mailbox.hpp"
#include <iostream>
#include <cstring>
#include <string>
#include <thread>
#include <chrono>
#include <fstream>

#if defined(__linux__)
#include <unistd.h>
#elif defined(_WIN32)
#include <windows.h>
#endif

inline uint32_t bswap32(uint32_t val) {
    return (val << 24) | ((val & 0xFF00) << 8) | ((val >> 8) & 0xFF00) | (val >> 24);
}

struct RpcInterface {
    volatile uint32_t execute_func;
    uint32_t func_addr;
    uint32_t r3, r4, r5, r6, r7, r8, r9, r10;
    uint32_t is_injecting;
};

uint64_t g_memoryBase = 0;
Mailbox* g_mailbox = nullptr;
RpcInterface* g_rpc = nullptr;
bool g_isInjecting = false;
bool g_hookInitialized = false;

static void writeDebugMsg(const char* msg) {
    if (!g_mailbox) return;
    std::strncpy(g_mailbox->debug_msg, msg, 63);
    g_mailbox->debug_msg[63] = '\0';
}

bool findMailbox() {
#if defined(__linux__)
    std::ifstream maps("/proc/self/maps");
    std::string line;
    while (std::getline(maps, line)) {
        if (line.find("rw-p") == std::string::npos && line.find("rw-s") == std::string::npos) continue;
        size_t dash = line.find('-');
        size_t space = line.find(' ');
        if (dash == std::string::npos || space == std::string::npos) continue;
        
        uint64_t start = std::stoull(line.substr(0, dash), nullptr, 16);
        uint64_t end = std::stoull(line.substr(dash + 1, space - dash - 1), nullptr, 16);
        uint64_t size = end - start;
        
        if (size >= 1024ULL * 1024 * 1024 && size <= 1500ULL * 1024 * 1024) {
            g_memoryBase = start - 0x10000000;
        }

        if (size > 2000ULL * 1024 * 1024) continue; // Skip huge mappings

        uint32_t* ptr = reinterpret_cast<uint32_t*>(start);
        uint32_t* endPtr = reinterpret_cast<uint32_t*>(end - 8);
        while (ptr <= endPtr) {
            if (ptr[0] == 0x41504D42 && ptr[1] == 0x424F5457) {
                g_mailbox = reinterpret_cast<Mailbox*>(ptr);
                g_rpc = reinterpret_cast<RpcInterface*>(reinterpret_cast<uint8_t*>(ptr) + 0x3020);
                return true;
            }
            ptr++;
        }
    }
#endif
    return false;
}

std::string readGuestString(uint32_t guestAddr) {
    if (guestAddr == 0) return "";
    char* hostPtr = reinterpret_cast<char*>(g_memoryBase + guestAddr);
    return std::string(hostPtr);
}

void hookLoop() {
    std::cout << "[BotW AP] Host DLL Thread Started. Waiting for Codecave..." << std::endl;
    while (!findMailbox()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
    
    std::cout << "[BotW AP] Mailbox Found in Codecave!" << std::endl;

    while (true) {
        std::this_thread::sleep_for(std::chrono::milliseconds(16));
        
        if (!g_mailbox || g_mailbox->magic_1 != bswap32(MAILBOX_MAGIC_1)) continue;
        
        if (!g_hookInitialized) {
            writeDebugMsg("Host DLL Injector Active!");
            std::cout << "[BotW AP] DLL Hook initialized." << std::endl;
            g_hookInitialized = true;
        }

        uint32_t in_tail = bswap32(g_mailbox->in_tail);
        uint32_t in_head = bswap32(g_mailbox->in_head);

        while (in_tail < in_head) {
            uint32_t index = in_tail % 256;
            IncomingItem& item = g_mailbox->incoming_queue[index];

            while (g_rpc->execute_func == bswap32(1)) {
                std::this_thread::yield();
            }

            uint32_t actSysPtr = bswap32(*reinterpret_cast<uint32_t*>(g_memoryBase + 0x105B8C00));
            if (actSysPtr != 0) {
                uint32_t strGuestAddr = (reinterpret_cast<uint64_t>(&item) - g_memoryBase) + 8;
                
                std::cout << "[BotW AP] Granting AP Item to Engine..." << std::endl;
                
                g_rpc->func_addr = bswap32(0x03741B20); // ksys::act::acquireItem
                g_rpc->r3 = bswap32(actSysPtr);
                g_rpc->r4 = bswap32(strGuestAddr);
                g_rpc->r5 = item.quantity;
                
                // Fire the RPC
                g_rpc->execute_func = bswap32(1); 
                
                while (g_rpc->execute_func == bswap32(1)) {
                    std::this_thread::yield();
                }
                writeDebugMsg("Granted AP Item!");
                std::cout << "[BotW AP] AP Item Granted." << std::endl;
            } else {
                std::cout << "[BotW AP] Engine not ready for item grant." << std::endl;
            }
            in_tail++;
            g_mailbox->in_tail = bswap32(in_tail);
        }
    }
}

#if defined(__linux__)
__attribute__((constructor))
void initHook() {
    std::thread(hookLoop).detach();
}
#endif
