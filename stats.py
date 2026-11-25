import emergent as E, statistics as st
def jac(a,b):
    a,b=set(a),set(b); return len(a&b)/len(a|b) if (a|b) else float('nan')
cfg=[("открытая, память ВКЛ",0.5,True),("открытая, память ВЫКЛ",0.5,False),("закрытая, память ВКЛ",0.0,True),("закрытая, память ВЫКЛ",0.0,False)]
rows=["| режим | доля с формой |𝔉|≥2 | медиана |𝔉| | устойчивость 𝔉 (Жаккар 2000→3000), медиана | медиана типов в W |","|---|---|---|---|---|"]
for name,inf,mem in cfg:
    F=[];J=[];T=[]
    for sd in range(1,21):
        w=E.World(seed=sd,inflow=inf,memory=mem); w.run(2000); F1=w.organization(); w.run(1000); F2=w.organization()
        F.append(len(F2)); T.append(len(set(w.W)))
        if len(F1)>=2 or len(F2)>=2: J.append(jac(F1,F2))
    rows.append(f"| {name} | {sum(f>=2 for f in F)}/20 | {st.median(F)} | {st.median(J):.2f} (n={len(J)}) | {st.median(T)} |")
    print(rows[-1],flush=True)
open('STATS.md','w').write("# SKI-модель, 20 seed на режим, T=3000\n\n"+"\n".join(rows)+"\n")
