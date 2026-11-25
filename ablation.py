import emergent as E, statistics as st
def jac(a,b):
    a,b=set(a),set(b); return len(a&b)/max(1,len(a|b)) if (a or b) else float('nan')
out=["# Абляция памяти (8 seed, inflow=0.5; F на t=2000 и t=3000)\n"]
for mem in (True, False):
    sizes=[]; pers=[]
    for sd in range(1,9):
        w=E.World(seed=sd,inflow=0.5,memory=mem)
        w.run(2000); F1=w.organization(); w.run(1000); F2=w.organization()
        sizes.append(len(F2))
        if F1 or F2: pers.append(jac(F1,F2))
    out.append(f"- memory={mem}: |F(3000)| по seed = {sizes}, среднее {st.mean(sizes):.1f}; устойчивость F (Жаккар 2000→3000) среднее {st.mean(pers):.2f}")
open('ABLATION.md','w').write("\n".join(out)+"\n"); print("\n".join(out))
