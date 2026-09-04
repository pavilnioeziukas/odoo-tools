# Temporary Odoo bootstraps

Šiame kataloge laikomi kontroliuojami, laikinai į Odoo aplinką įdiegiami techninės priežiūros veiksmai. Jie nėra nuolatinė Odoo konfigūracija.

## Pristatyto kiekio pataisymas

Modulis: `odoo_tools.bootstraps.sale_delivered_manual`

Jis laikinai sukuria kontekstinį veiksmą pardavimo užsakymo eilutėms. Veiksmas:

- leidžiamas tik patvirtintoms SO eilutėms, kurių `Delivered = 0`;
- reikalauja bent vieno užbaigto susieto sandėlio judėjimo;
- neleidžia vykdyti, kol yra neužbaigtų susietų judėjimų;
- nustato `qty_delivered_method = manual` ir `qty_delivered = product_uom_qty`;
- nekeičia sandėlio judėjimų, atsargų ar FIFO.

### Privaloma darbo eiga

1. Patikrinti SO, produktą, realų pristatymą ir visus susijusius judėjimus.
2. Pirmiausia įdiegti ir išbandyti `stage` aplinkoje.
3. Produkcijoje nustatyti prisijungimo kintamuosius ir vienai komandai papildomai:

   `ODOO_BOOTSTRAP_CONFIRM=DEPLOY_TEMPORARY_ODOO_BOOTSTRAP`

4. Įdiegti, aiškiai patvirtinant tikslų hostą:

   `python -m odoo_tools.bootstraps.sale_delivered_manual install --confirm-host odoo.furnix.lt`

5. Odoo pardavimo eilučių sąraše pažymėti tik iš anksto patikrintas eilutes ir paleisti veiksmą `[odoo-tools] Repair delivered quantity (temporary)`.
6. Perkrauti puslapį ir patikrinti rezultatą.
7. Nedelsiant pašalinti veiksmą:

   `python -m odoo_tools.bootstraps.sale_delivered_manual uninstall --confirm-host odoo.furnix.lt`

Diegimas yra idempotentinis. Pašalinimas naudoja valdomą XML ID ir atsisako trinti veiksmą, jei jo pavadinimas arba kodas buvo pakeistas rankiniu būdu.
