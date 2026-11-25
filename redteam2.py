import statistics as st
from chem import Chem
rows=["| p | форма с расщеплением | форма только лигированием (строго: каждый вид собран из других, катализатор внутри формы) |","|---|---|---|"]
for p in (0.02,0.05,0.12):
    a=[];b=[]
    for sd in range(1,21):
        c=Chem(seed=sd,p=p).run(150000); a.append(len(c.organization())); b.append(len(c.organization(cleave=False)))
    rows.append(f"| {p} | {sum(x>=2 for x in a)}/20 (мед. {st.median(a)}) | {sum(x>=2 for x in b)}/20 (мед. {st.median(b)}) |")
    print(rows[-1],flush=True)
open('REDTEAM_chem_strict.md','w').write("\n".join(rows)+"\n")
