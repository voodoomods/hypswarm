# Disclaimer

## Provided as is

HypSwarm is provided **as is, without warranty of any kind**, under the
[Apache License 2.0](https://github.com/voodoomods/hypswarm/blob/main/LICENSE). Sections 7 and 8 of that licence
(Disclaimer of Warranty, Limitation of Liability) apply to the code, the documentation, the examples, the studies and
the website.

## It spends your money

HypSwarm runs AI agents with the model provider and key you give it. Every call is billed
to you by that provider, at that provider's prices. A run's budget (calls, dollars) is enforced by HypSwarm's own
count of tokens and prices, which can differ from what the provider bills; treat it as a limit that is best effort,
not a guarantee, and set a spending cap with your provider too.

## It runs code a model wrote

Seats can write and run code. The default sandbox is a subprocess with a time limit
on your machine: it runs as you, with your files and your network. It is not a security boundary. Run untrusted
work in a sandbox you trust, such as a container or [HypDMZ](https://hypdmz.com).

## Agents make mistakes

The record refuses some overclaims as they are written, and standing is derived, not
certified (see the [HypGraph disclaimer](https://hypgraph.com/disclaimer/)). A swarm's claims, reports and code can
still be wrong. Check what they say before you act on it. Nothing a swarm produces is legal, medical, financial or
investment advice; the trading profile works on paper positions and historical data.

## You are responsible for what your agents do

That includes what they send to a model provider, what they fetch, what they write to a shared or public record, and
whether that complies with your provider's terms and your own obligations.

## No affiliation

HypSwarm works with OpenAI-compatible APIs. It is not affiliated with or endorsed by OpenAI or
any other model provider; their names are used only to say what HypSwarm can connect to.

HypSwarm is made by VoodooMods LLC. Questions: open an issue at https://github.com/voodoomods/hypswarm/issues.
