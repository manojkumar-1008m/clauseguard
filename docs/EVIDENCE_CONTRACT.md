# ClauseGuard Evidence Contract

`EvidenceItem` is the canonical atomic evidence record. It carries source, type, description, strength, model confidence, provenance, journey, decision context, temporal position, route, route sequence, event indices, and browser metadata.

Evidence Fusion accepts text, price, DOM, behavior, image, and raw evidence payloads. Vision output is observation evidence with model provenance and confidence; it is not an independent final risk result.

Adapters normalize contexts such as cart and basket to checkout and preserve explicit metadata when present. Extension payload construction remains incomplete because journey, tab, product, and route metadata are not consistently forwarded.
