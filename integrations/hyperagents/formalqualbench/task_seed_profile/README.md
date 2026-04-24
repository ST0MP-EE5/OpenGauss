# OpenGauss Native FormalQualBench Base

Benchmark-only HyperAgents seed profile for the native OpenGauss FormalQualBench lane.

This profile does not change OpenGauss runtime code. It only provides the mutable benchmark bundle consumed by the OpenGauss FormalQualBench evaluator under:

- `workspace/opengauss_formalqualbench/instructions.md`
- `workspace/opengauss_formalqualbench/startup_context.md`
- `workspace/opengauss_formalqualbench/theorem_hints/*.md`

The intended systems are:

- `opengauss-gpt55-direct`
- `opengauss-gpt55-hyper-promoted`
