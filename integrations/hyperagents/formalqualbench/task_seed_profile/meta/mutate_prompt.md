# Mutation Contract

You are improving the native OpenGauss benchmark lane for FormalQualBench.

Hard boundaries:
- mutate only files under `workspace/opengauss_formalqualbench/**`
- do not modify OpenGauss runtime code, FormalQualBench challenge files, or Comparator policy/config semantics
- do not add a new outer runtime or a separate CLI path

Primary objective:
- increase Comparator-verified solve count on the sanity slice

Secondary objectives:
- reduce total wall-clock time
- keep native runs at zero MCP/proxy calls

Preferred mutations:
- sharpen native OpenGauss workflow instructions
- improve startup context framing
- add theorem-local hints for the target tasks
- tighten benchmark-side retry/budget guidance if it stays within the same benchmark contract
