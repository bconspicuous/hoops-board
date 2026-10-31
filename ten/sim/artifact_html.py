"""Write out/league10.html (artifact version of the dashboard) from ten/index.html by removing the GitHub-Pages noindex prefix."""
import os
W = os.path.dirname(os.path.abspath(__file__)) + '/'
s = open(os.path.join(W, '..', 'index.html'), encoding='utf-8').read()
open(W + 'out/league10.html', 'w', encoding='utf-8').write(s[s.index('<title>'):])
print(W + 'out/league10.html')
