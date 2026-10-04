using System;
using Archipelago.MultiClient.Net;
using Archipelago.MultiClient.Net.Enums;
using BotWClient.Memory;

namespace BotWClient.Archipelago
{
    public class APSessionManager
    {
        private ArchipelagoSession _session;
        private CemuMemoryReader _memoryReader;

        public APSessionManager(string uri, string slotName, CemuMemoryReader memoryReader)
        {
            _session = ArchipelagoSessionFactory.CreateSession(uri);
            _memoryReader = memoryReader;
            
            var result = _session.TryConnectAndLogin("Breath of the Wild", slotName, ItemsHandlingFlags.AllItems);
            
            if (result.Successful)
            {
                Console.WriteLine("Connected to Archipelago!");
                _session.Items.ItemReceived += OnItemReceived;
            }
            else
            {
                Console.WriteLine("Failed to connect to Archipelago.");
            }
        }

        private void OnItemReceived(global::Archipelago.MultiClient.Net.Helper.ReceivedItemsHelper helper)
        {
            var item = helper.DequeueItem();
            Console.WriteLine($"Received item: {item.ItemName}");
            // Route to memory reader
            _memoryReader.WriteIncomingItem(new IncomingItem 
            { 
                ApItemId = (uint)item.Item,
                ActorName = "Weapon_Sword_001", // Placeholder translation
                Quantity = 1
            });
        }

        public void DispatchLocationCheck(OutgoingCheck check)
        {
            Console.WriteLine($"Dispatching check: {check.ApLocationId}");
            _session.Locations.CompleteLocationChecks((long)check.ApLocationId);
        }
    }
}
