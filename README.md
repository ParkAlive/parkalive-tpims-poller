# Park Alive TPIMS poller

Raccoglie ogni 15 minuti disponibilità, capienza e stato dei parcheggi camion
pubblicati dai feed TPIMS di Illinois, Indiana e Kentucky. Associa inoltre il
meteo NWS corrente alle stazioni dotate di coordinate.

Minnesota e Ohio sono raccolti separatamente dal collector privato Park Alive
tramite i nuovi endpoint ufficiali; i vecchi feed presenti in questo progetto
non sono più raggiungibili e sono stati rimossi.

Ogni chiamata di rete ha un timeout breve, il meteo viene interrogato in
parallelo e ogni ciclo ha un limite massimo di dieci minuti.
