# odoo-tools

Bendri, nuo konkretaus kliento nepriklausomi Odoo įrankiai.

Pagrindinė biblioteka ir ataskaitos yra tik skaitymui. Aiškiai izoliuoti laikini techninės priežiūros veiksmai laikomi [`odoo_tools/bootstraps`](odoo_tools/bootstraps/README.md); jų diegimui ir pašalinimui privalomas atskiras, vienai komandai suteikiamas patvirtinimas.

Pirmoji bibliotekoje iškelta ataskaita – sandėlio likučiai pagal konfigūruojamas lokacijas. Ji taip pat rodo prekės kategoriją ir patvirtintuose PO dar negautą kiekį (`purchase` / `done`, užsakyta minus faktiškai gauta), konvertuotą į produkto matavimo vienetą.

Reusable read-only Odoo clients and reports, plus explicitly deployed temporary maintenance bootstraps.
