# Proxy Delay Evaluation

This repository contains code and workflows related to the emulated and real-world experiments in: [*Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays*](https://nines-conference.org/papers/p027-Illick.pdf).


## Repository Scope

- `emulated-repro/`
  - Code to reproduce emulated experiments in *Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays*.
- `emulated/`
  - Generalized emulated experimentation framework: starter code to run new emulated experiments using this framework and analyze the impact of propagation delay in more settings.
- `real-world/`
  - Framework for running real-world tests with your own topology and infrastructure. Code to run real world experiments following our methodology in *Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays*. 

## Reproducibility Note

The emulated reproduction pipeline (`emulated-repro/`) reproduces the emulated results from the paper exactly.

For real-world testing (`real-world/`), this code provides methodology and tooling to produce similar real-world experiments. Real-world outcomes dependend on deployment context, including endpoint locations, access-network characteristics, routing conditions, and institutional infrastructure. The provided code is intended to enable rigorous replication of methodology and to support follow-on work in new environments.

## Setup and Usage

All setup and run instructions are in subfolder READMEs:

- Emulated reproduction: `emulated-repro/README.md`
- Emulated exploration framework: `emulated/README.md`
- Real-world methodology framework: `real-world/README.md`
