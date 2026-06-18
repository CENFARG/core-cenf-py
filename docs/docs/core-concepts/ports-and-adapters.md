# Ports &amp; Adapters Architecture

Every manager has exactly one **Protocol** (port) and one or more **Adapters** (implementations). Your code depends on the Protocol. The adapter is injected at startup.
