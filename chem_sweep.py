import statistics as st
from chem import Chem
P=(0.01,0.02,0.03,0.05,0.08,0.12); S=range(1,21)
rows=["| p | inflow | доля прогонов с формой 𝔉 (|𝔉|≥2) | медиана |𝔉| | медиана новых видов |","|---|---|---|---|---|"]
for inflow in (0.1, 0.0):
    for p in P:
        F=[];N=[]
        for sd in S:
            c=Chem(seed=sd,p=p,inflow=inflow).run(150000); F.append(len(c.organization())); N.append(c.new)
        rows.append(f"| {p} | {inflow} | {sum(f>=2 for f in F)}/{len(F)} | {st.median(F)} | {st.median(N)} |")
        print(rows[-1],flush=True)
open('CHEM_RESULTS.md','w').write("# Реакционная сеть (независимая реализация той же формулы)\n\nM=300, L=6, T=150000, 20 seed на строку. Катализ — фиксированная псевдослучайная таблица (вероятность p).\n\n"+"\n".join(rows)+"\n")
