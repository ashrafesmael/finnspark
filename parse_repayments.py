import re
from datetime import datetime

raw_data = """
10/08/2026 Ms. Saud Battikeh 1000014 Wafaa Sakriyeh Online Transfer 31,778.00
21/07/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
22/07/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
23/07/2026 Mrs. Randa Kamal Rezqi Elayyan 1000009 Wafaa Sakriyeh Cash 57,000.00
27/07/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
04/08/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
21/07/2026 Mr. Moayad Mahmoud Abed Al-Najdawi 1000011 Wafaa Sakriyeh Online Transfer 44,240.00
26/07/2026 Miss Aseel Ihssan Mahmoud Yaseen 1000012 Wafaa Sakriyeh Online Transfer 47,600.00
27/07/2026 Kafana Systems and Software Company / Limited Liability 1000010 Wafaa Sakriyeh Online Transfer 42,780.00
28/07/2026 Ms. Shorouq AlMazraawi 1000015 Wafaa Sakriyeh Online Transfer 31,600.00
20/07/2026 Mr. Amer Ibrahim Aref Alaabed 1000013 Wafaa Sakriyeh Online Transfer 1,043.65
14/07/2026 Mr. Amer Ibrahim Aref Alaabed 1000013 Wafaa Sakriyeh Online Transfer 42,858.00
01/07/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
01/07/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
18/06/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
23/06/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
28/06/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 finnpact Administrator Online Transfer 5,353.89
28/06/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 49,000.00
13/05/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
21/05/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
21/05/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
02/06/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
04/06/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
15/04/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
19/04/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
27/04/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
28/04/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
26/04/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
17/03/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
19/03/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
24/03/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
26/03/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
26/03/2026 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
26/03/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
03/03/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Cash 48,900.00
02/03/2026 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
01/03/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
15/02/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
22/02/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
23/02/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
31/01/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,900.00
15/01/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
26/01/2026 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
27/01/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
28/01/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
01/02/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
16/12/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
16/12/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
18/12/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
22/12/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
23/12/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
24/12/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
03/12/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
17/11/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
18/11/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
24/11/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
24/11/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
30/11/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
28/10/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Online Transfer 48,000.00
16/10/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
20/10/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
22/10/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
23/10/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
21/10/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
23/09/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
15/09/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
22/09/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
23/09/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
23/09/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
24/09/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
19/08/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Online Transfer 32,230.00
24/08/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Online Transfer 48,925.00
13/08/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Natasha Dokhgan Online Transfer 48,800.00
18/08/2025 Mr. Saqr Bassam Ali Marayha 1000007 Natasha Dokhgan Online Transfer 48,000.00
14/08/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Natasha Dokhgan Online Transfer 48,435.00
18/08/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
21/07/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
24/07/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
27/07/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,925.00
15/07/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,724.00
16/07/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
20/07/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
24/06/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Natasha Dokhgan Online Transfer 8,150.00
02/07/2025 Mr. Saqr Bassam Ali Marayha 1000007 Natasha Dokhgan Online Transfer 8,100.00
"""

lines = [l.strip() for l in raw_data.strip().split('\n') if l.strip()]
print(f"Total lines parsed: {len(lines)}")

records = []
for l in lines:
    # Match: DD/MM/YYYY [Name] [Loan#] [Collector] [Method] [Amount]
    m = re.match(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(1000\d{3})\s+(Wafaa Sakriyeh|Natasha Dokhgan|finnpact Administrator)\s+(Online Transfer|Cash)\s+([\d,]+\.\d{2})$", l)
    if not m:
        print("FAILED TO MATCH:", l)
    else:
        dt_str, name, loan_no, collector, method, amt_str = m.groups()
        amt = float(amt_str.replace(",", ""))
        dt = datetime.strptime(dt_str, "%d/%m/%Y").date()
        records.append({
            "date": dt,
            "name": name,
            "loan_no": loan_no,
            "collector": collector,
            "method": method,
            "amount": amt,
        })

print(f"Successfully converted: {len(records)} records.")
print(f"Total amount sum: {sum(r['amount'] for r in records):,.2f}")
