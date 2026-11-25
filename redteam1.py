import emergent as E, statistics as st
# Дыра 2: проекции (K a b -> a) дают «самопроизводство» без творчества. strict: результат не подтерм реагентов.
rows=["| режим | доля с формой (обычная) | медиана |F| обычная | доля с формой (strict) | медиана |F| strict |","|---|---|---|---|---|"]
for name,inf,mem in [("открытая, память ВКЛ",0.5,True),("открытая, память ВЫКЛ",0.5,False),("закрытая, память ВЫКЛ",0.0,False)]:
    a=[];b=[]
    for sd in range(1,21):
        w=E.World(seed=sd,inflow=inf,memory=mem).run(3000)
        a.append(len(w.organization())); b.append(len(w.organization(strict=True)))
    rows.append(f"| {name} | {sum(x>=2 for x in a)}/20 | {st.median(a)} | {sum(x>=2 for x in b)}/20 | {st.median(b)} |")
    print(rows[-1],flush=True)
open('REDTEAM_strictF.md','w').write("\n".join(rows)+"\n")
