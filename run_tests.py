import test_emergent as T, traceback
ok=0
for n in [x for x in dir(T) if x.startswith('test_')]:
    try:
        getattr(T,n)(); print('PASS',n); ok+=1
    except Exception:
        print('FAIL',n); traceback.print_exc()
print(ok,'passed')
