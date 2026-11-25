import statistics as st
from chem import Chem
def jac(a,b):
    a,b=set(a),set(b); return len(a&b)/len(a|b) if (a|b) else float('nan')
rows=["| режим (p=0.08, 20 seed) | доля с формой | медиана |F| | устойчивость F (Жаккар 100k→150k) |","|---|---|---|---|"]
for name,mem,inf in [("открытая, память ВКЛ",True,0.1),("открытая, память ВЫКЛ",False,0.1),("закрытая, память ВКЛ",True,0.0),("закрытая, память ВЫКЛ",False,0.0)]:
    F=[];J=[]
    for sd in range(1,21):
        c=Chem(seed=sd,p=0.08,memory=mem,inflow=inf); c.run(100000); a=c.organization(cleave=False); c.run(50000); b=c.organization(cleave=False)
        F.append(len(b))
        if len(a)>=2 or len(b)>=2: J.append(jac(a,b))
    rows.append(f"| {name} | {sum(x>=2 for x in F)}/20 | {st.median(F)} | {st.median(J):.2f} (n={len(J)}) |"); print(rows[-1],flush=True)
open('REDTEAM_chem_memory.md','w').write("\n".join(rows)+"\n")
