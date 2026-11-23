# Receiving webhook events

Ruth Calder, integrations engineer

Register an HTTP or HTTPS URL for each subscription. We POST the event bytes to
its path and query string. Explicit ports from 1 through 65535 are supported,
including receiver ports such as 8443 and 9000. Schemes use ordinary HTTP/HTTPS
spelling and explicit ports use decimal digits. URLs cannot contain usernames
or passwords, or ambiguous backslashes in the authority.

You can save a hostname subscription while your receiving team provisions its
DNS record. Saving the URL does not authorize future addresses. Each published
event keeps its queued destination and event bytes; changing a subscription URL
applies to future events. If DNS is unavailable at delivery, the attempt fails
and follows our normal retry policy. A destination refused by the public-address
policy stops that delivery instead. Each later attempt uses and authorizes the
current addresses of its queued destination. Queued events and scheduled retries
survive service maintenance and restarts, keeping their destination, event bytes
and attempt history. A resumed attempt applies the public-address policy again.

An event creates a separate queued delivery for every matching subscription.
One receiver's refusal does not stop deliveries to the others. Subscriptions can
share a regional gateway, but its handoff cookies remain private to each
delivery, including when those subscriptions belong to different customers.

Some receiving gateways send informational HTTP responses while preparing their
answer. A warehouse gateway, for example, may send 102 Processing while its
regional intake prepares the event receipt. This progress does not acknowledge
the event or count as a redirect. During a receiver restart or an interrupted
gateway exchange, the connection can close after an acceptance status but before
the headers finish. The final headers must reach their terminating empty line,
even if all apparent fields have arrived. Unfinished headers mean a failed
attempt; we do not follow an unfinished regional handoff. Once the final headers
are complete, they supply the delivery result and any regional handoff, including
its applicable cookie. Some gateways append diagnostic text for their operators,
with a declared length or in chunks. An interruption of that text does not erase
the returned acceptance or refusal, or cancel the completed handoff.

An intake can also answer from the event headers, before it consumes the upload.
For example, a warehouse gateway can refuse an oversized event with 413 while
the upload is in progress. That completed answer is the result even if the
local upload write fails. A completed regional handoff works the same way:
the accepting destination receives the original full event, with the applicable
handoff cookie. Without complete final headers, the exchange fails.

Your receiver may redirect with 301, 302, 303, 307 or 308. We send the same POST
and event body at the destination. Relative destinations, such as `/hooks/new`
or `next`, are resolved against the current URL. We follow up to three redirects;
a fourth redirect ends the delivery with an error. Regional gateways can use
response cookies for a temporary event handoff. We honor the deployed sender's
Domain, Path, Secure and expiry rules, including replacement at the same scope
and deletion. Those cookies belong only to that delivery; later calls start
without them, even if the earlier delivery ended in an error. A delivery that
starts with HTTPS cannot continue over plain HTTP. HTTPS verifies the certificate
chain and the DNS name in each URL. A terminal root dot makes a receiving DNS
name absolute, excluding the sending node's search suffixes. This applies to
registrations and regional destinations alike. The HTTP Host may retain that
dot, while TLS uses the DNS name without it.

Internationalized registrations use the DNS A-label for the receiver's identity,
including certificate verification. Ordinary ASCII regional names such as
us--west.parcelspan.eu keep their receiving identity, including when another
label is already an A-label. Partner exports also spell ordinary DNS label
characters with unreserved percent escapes; these registrations and redirect
destinations identify the same receiving host, including its receiver cookies.
The signed path and query keep their own spelling. Accented path and
query text travels as UTF-8 percent escapes. Escaped separators remain escaped,
and repeated query parameters keep their order: receivers may sign those exact
request-target bytes. A redirect's UTF-8 Location and its escaped ASCII spelling
identify the same route. Our [partner routing correspondence](receiver-routing.eml)
gives a shipping integration example of these registrations.

Receivers must be on the public internet. This applies when an event is sent,
including every redirect, rather than only when you register a subscription.
An IPv4 literal must use ordinary dotted decimal; legacy integer, octal and
hexadecimal IPv4 forms are not accepted. Standard IPv6 literals are supported
without interface or zone suffixes: an interface identifier belongs to the
sending machine, not the receiver's public address.
IPv4-mapped IPv6 is classified by its enclosed IPv4 address. A hostname is refused
if any of its resolved addresses is non-public, even when another address is
public.

An address must be global under Python 3.11's address classification and cannot
be multicast, reserved or unspecified. We also exclude shared, special-purpose,
benchmark, translation and local ranges: 100.64.0.0/10, 192.0.0.0/24,
198.18.0.0/15, 64:ff9b::/96, 2002::/16, fc00::/7 and fe80::/10. These restrictions
keep customer events away from internal services and infrastructure endpoints.
