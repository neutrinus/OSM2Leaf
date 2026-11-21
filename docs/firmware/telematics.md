# Telematics (Carwings client)

Static map of the head unit's Carwings telematics stack in build A:
`Telema.exe`, `ComMid.exe`, the `Telema*CC` screens, `Cws_Apl.dll`,
`Prb_Apl.dll` and `DCM_API.dll`. Side track (task M1.45): it does not block the
map compiler. **No network traffic is generated**; everything below comes from
the image headers and from strings/decoding of the stored bytes.

VAs are module-relative and name the build: `eu2011` is
`archive/head256.img` (SHA-256 `92aa525d…07f9`, the 256 MiB firmware head of
the EU 2011 card), `us2011` is `archive/us256.img` (SHA-256
`70d945d8…04da`). Both `Telema.exe` builds use
module `vbase=0x00010000`, so a VA reads the same way in either image; the two
builds are nevertheless a separate module instance and every row below says
which one it was measured on.

Evidence: EXP-2026-11-21-M1.45-telematics-endpoints; claims C-6470–C-6479.
Status classes follow [`README.md`](README.md): VERIFIED (a command printed it)
/ OBSERVED (strings or code shape, one reading) / HYPOTHESIS.

## 1. Modules

| Module | ROM | Size | Role (one line) | Evidence |
| --- | --- | --- | --- | --- |
| `Telema.exe` | A | 1 138 176 B | The Carwings application: connection state machine, HTTP client, XML DOM, endpoint table, `DLJ`↔`DCC`/`DCM`/`APL` message dispatch. | `cerom.py modules`; strings below |
| `Cws_Apl.dll` | A | 26 624 B | Application (APL) side: builds the Carwings data-request messages (route, charging points, DJ, traffic) and reads the received data. | `cerom.py exports Cws_Apl.dll` |
| `Prb_Apl.dll` | A | 9 216 B | Probe (floating-car data) request side: auto-send, history change/clear, initial request. | `cerom.py exports Prb_Apl.dll` |
| `DCM_API.dll` | A | 16 384 B | The Data Communication Module (TCU) API. Exports `Dial`, `HangUp`, `ReadDCMConnectStatus`, `GetOperatorInfo`, `GetSIMID`, `GetVINCode`, `GetMSN`, `ReadAntennaLevel`, `SetVehicleData`, `ActivateDCM`, … `Telema.exe` imports the status/ID half; `PhoneBTA.exe` imports `Dial`/`HangUp`. | `cerom.py exports DCM_API.dll`; `cerom.py imports …` |
| `ComMid.exe` | A | 122 880 B | Communication-middleware host process (`Oscl`/`Utility` logger and IPC exports). Its exact message routing is not decoded here. | `cerom.py exports ComMid.exe` (HYPOTHESIS on role) |
| `Telema*CC.dll` ×19 | A | 4–200 KB | Carwings screens (`TelemaAdjCC`, `TelemaAdjHisCC`, `TelemaAdjSetCC`, `TelemaAutoplayCC`, `TelemaAutoplayCCLib`, `TelemaCarwingsCC`, `TelemaCCWrapper`, `TelemaCntsListCC`, `TelemaCPCC`, `TelemaDCMSetCC`, `TelemaDLCC`, `TelemaDLCCLib`, `TelemaDLSetCC`, `TelemaFvtCC`, `TelemaFvtRegCC`, `TelemaImageDrawCC`, `TelemaRegPntCC`, `TelemaRouteCC`, `TelemaTelCallCC`). They call `Cws_Apl`/`Prb_Apl`; no transport code of their own. | `cerom.py modules` (`grep -c` 19) |

`Telema.exe` has 3 sections in both builds: `sec0` is the only uncompressed
executable section (EU vsize `0x10a7e2`; US `0x10c9fc`); `sec1`/`sec2` are
compressed `.data` and are out of scope for this page (strings are in `sec0`,
which is where all evidence below is read).

## 2. Transport

`Telema.exe` never opens a serial device and never dials. It imports
`WS2.dll` (the full socket API: `socket`, `ioctlsocket`, `connect`, `send`,
`recv`, `select`, `getaddrinfo`, `closesocket`) and only the *status/ID* half of
`DCM_API.dll` (`Init`, `set`, `GetOperatorInfo`, `ReadVINCode`, `ReadPIN`,
`ReadMSN`, `ReadSIMID`, `ReadDCMID`, `ReadDCMVer`, `ReadAntennaLevel`,
`ReadServiceArea`, `?ReadDCMConnectStatus…`, `?ActivateDCM…`), not
`Dial`/`HangUp`. The
actual dial is done by **`PhoneBTA.exe`** (697 856 B, `vbase=0x00010000`),
which is the only module in build A importing `DCM_API!Dial` and
`DCM_API!HangUp` (`slot=0x000b11bc/0x000b11b8`); `Telema.exe` reaches it through
the phone/DCM IPC path (`CPhoneBTAAccess::ReqDialByDCM()` at `0x0008584c`,
`CSpcomIpcMsg Connect Error` at `0x000854cc`). The physical bearer is one of:

| Bearer | Evidence | Module (eu2011) | Status |
| --- | --- | --- | --- |
| TCU / DCM (`DCM_API`) | `DCM_API!Dial`, `DCM_API!HangUp` imports | `PhoneBTA.exe` slots `0x000b11bc`/`0x000b11b8` | VERIFIED (imports) |
| TCU status/IDs | `DCM_API!GetOperatorInfo`, `?ReadDCMConnectStatus…`, `ReadVINCode`; `[%8d]ms <DLJ->DCM> Req GetOperatorInfo` at `0x000232c8` | `Telema.exe` | VERIFIED (imports/strings) |
| Phone over Bluetooth DUN | `BT(DUN)` at `0x00011568`; `BT_WRPENG!?Bt_OpenDunEngine…`; `BT_DB!…` | `Telema.exe` (`BT_WRPENG.dll`/`BT_DB.dll`) | VERIFIED (imports/strings) |
| RAS / PPP dial-up | `DCC_RASSTEP_*` (`0x00018b40`, `0x00018b6c`); `PPP INFO` at `0x00022938`; `AT+CGDCONT`, `AT+CGDCONT?`, `AT+CGDCONT=` at `0x00013044`/`0x00013054`/`0x0001309c` | `Telema.exe` | VERIFIED (strings) |
| HTTP over the established link | `HTTP/1.0` `HTTP/1.1` (`0x0003bc48`), `CONNECT` (`0x0003c08c`), `http-client`/`http-%d` (`0x0003c06c`), response codes `400/413/500/505` (`0x0002c5cc` …) | `Telema.exe` | VERIFIED (strings) |

The control hierarchy visible in strings is
`APL (Cws_Apl/Prb_Apl) ↔ DLJ ↔ {DCC (RAS/AT/PPP), DCM (DCM_API), SDP}`; the
`<DLJ->…>` / `<…->DLJ>` prefixes at `0x000232c8`–`0x000262d8` name each hop.
`DCC` = the data-connection controller, `DLJ` = the data-line job that owns the
session, `DCM` = the telematics unit, `APL` = the Carwings application, `SDP`
= the speech-guide player.

## 3. Endpoints

All strings are ASCII in `Telema.exe` `sec0`. EU measured on
`archive/head256.img`, US on `archive/us256.img` (same command, different
image). Hosts marked "dev/QA" are factory-selected alternates printed by the
same endpoint-table builder; the unit picks one by configuration, not by
trying them all (OBSERVED).

| Kind | String | eu2011 VA | us2011 VA |
| --- | --- | --- | --- |
| Base URL | `biz.nissan-gev.com/WARCondelivbas/it-m_gw10/` (scheme `http://`) | `0x00021c9c` | `0x00021b54` |
| Base URL | `qa.nissan-gev.com/WARCondelivbas/it-m_gw10/` (scheme `http://`) | `0x000251d4` | (absent) |
| Host | `biz.nissan-gev.com` | `0x000252d0` | `0x000258f8` |
| Host | `dev.nissan-gev.com` | `0x000252e4` | `0x0002590c` |
| Host | `qa.nissan-gev.com` | `0x000251db` | (absent) |
| Host | `www.ev-itvc.jp` | `0x000252c0` | `0x000258e8` |
| Host | `drive1-dev.saas.secureonline.jp` | `0x000252f8` | `0x00025920` |
| Path | `/xanavi/cws.exe` | `0x00025318` | `0x00025940` |
| Path | `/xanavi/EV_cws.exe` | `0x00025334` | `0x0002595c` |
| Dispatcher | `service.caravelmap.jp/cic-web/dispatcher.exe` (scheme `http://`) | `0x00024f70` | `0x000255e0` |
| Host | `cwsxanavi.myhome.cx` | `0x00024fa4` | `0x00025614` |
| MIME | `application/x-carwings-nz` | `0x0002500c` | `0x0002567c` |
| APN | `Trial.globalm2m.net` | `0x000254f0` | `0x00025b04` |
| APN | `atxg.rogersm2m.apn` | `0x000254dc` | `0x00021b34` |
| APN | `bwv8g.dcm.ne.jp` (NTT DoCoMo) | `0x00025504` | `0x00025b18` |
| APN | `attz.atxg.com` | `0x0002555c` | `0x00021b1c` |
| APN | `bc572.dcm.ne.jp` | `0x0002556c` | `0x00025b94` |
| APN | `mopera.ne.jp` | `0x000255bc` | `0x00025be4` |
| APN | `ISPDA@CINGULARGPRS.COM` | `0x00025520` | `0x00025b48` |
| APN | `internet.connexion` | `0x00025548` | `0x00025b70` |

The same scan (`ce_strfind … --encoding ascii`, 18 needles) reported **19
hits** on EU and **18** on US (`biz.nissan-gev.com` matches twice in EU); the
one needle absent in US is `qa.nissan-gev.com`. So the endpoint *table* is
essentially the same in both builds, but the EU build carries a
`qa.nissan-gev.com` base-URL alternate the US build does not (VERIFIED by the
two hit counts). The string VAs differ between
builds even where the string is identical (`biz.nissan-gev.com` at
`0x000252d0` EU vs `0x000258f8` US), because `sec0` is a different size.

The endpoint-table builder is `fn 0x000b0d58` (eu2011) / `fn 0x000b1e68`
(us2011): it loads a module/site selector from `0x0069f410` (EU), tests it
against `63` (`0x3f`) after subtracting `11`, and formats the chosen host/path
pair; the "/xanavi/…" literals are byte-copied into the request struct.

## 4. Message types and request builders

Two layers are visible:

* **DLJ control messages** (session/transport), one request-emit function each:
  the function prepares a fixed-size (`80<<2 = 320`-byte) session record, fills
  the fields its request names, and traces through the same format string. The
  binary field layout of that record is not decoded here (HYPOTHESIS); the
  payload fields below are the ones the format string names and the function
  passes in registers.
* **APL data messages** (`Cws_Apl` exports): each `…_send…Req` builds a small
  record (`<u32 tag> <u32 len> <payload…>`) — e.g.
  `CWS_Apl_Adj_sendChnListReq` (`va 0x02661a2c`) writes tag `0xa5000001`, length
  `0x00008004` and the caller's buffer, then calls `0x02661770`. These are the
  requests that carry a Carwings data class (section 5).

### 4a. DLJ builders (≥ 3 request types, both builds)

Every builder VA below was printed by
`python3 tools/sh4xref.py IMG Telema.exe --image-start 0x200200 --to <string VA>`
(the `fn` of the `mov.l @(…,pc)` load), and the string VA by
`python3 tools/ce_strfind.py`.

| Request type | eu2011 builder | us2011 builder | Payload fields readable from strings |
| --- | --- | --- | --- |
| Open session | `0x000b2320` | `0x000b3474` | application id (`%d`), client port (`ClntPort[%d]`) — string `[%8d]ms <DLJ->DCC> Req CreateSession(%d) ClntPort[%d]` (EU `0x0002564c`, US `0x00025c74`) |
| Send data | `0x000b153c` | `0x000b264c` | data length (`SendData(%d)`); response `Res SendData(1)/(2) [%d][%d]` carries two status words (EU `0x00025490`) |
| Set APN | `0x000b126c` | `0x000b237c` | APN selection string; response `Res SetAPN [%d][%d][%d]` (EU `0x000253ec`) |
| Close session | `0x000b030c` | `0x000b15ac` | session id; response `Res CloseSession [%d][%d]` (EU `0x00025084`) |
| Get operator info | `0x000a6040` | `0x000a7328` | operator id; response `Res GetOperatorInfo [%d]` (EU `0x000232c8`, `<DLJ->DCM>` — this one goes to the TCU, not DCC) |

The "payload fields" are the values the format strings name and that the
request function passes in registers; the byte layout of the struct handed to
`DCC`/`DCM` is **not** decoded here (HYPOTHESIS on field order/size; the
function allocates a `80<<2 = 320`-byte session record, EU `0x000b2336`).

### 4b. Application (XML) request builder

`fn 0x000a738c` (eu2011) is the HTTP request-body builder: it checks an object
size of `68<<8`, writes the fixed XML prolog
`<?xml version="1.0" encoding="UTF-8" standalone="no"?>` (EU `0x000234a8`), then
copies the named message body from the file `cws_snd.xml` (`0x000235d0`). The
received body name `cws_rcv.xml` (`0x00023630`) is loaded by a separate
function, `fn 0x000a7b10`, not by `0x000a738c`. In us2011 the send role is
`fn 0x000a8674` (`cws_snd.xml` at `0x00023c88`) and the receive side
`fn 0x000a8df8` (`cws_rcv.xml` at `0x00023ce8`). The probe side
uses `prb_snd.xml` (`0x000235dc`). These are the **message envelope**: the
request is an XML document, not a binary payload, at the application layer.

## 5. Carwings data classes (message topics)

The `cws*` identifiers at EU `0x00026c1c`–`0x00026d70` name the data objects the
application request/receives (the message topics behind the APL requests):

`cwsDatalineinf`, `cwsCPwarning`, `cwsCPhome`, `cwsCPmanual`, `cwsCPstatus`,
`cwsTrfreqDLData`, `cwsDCMAutInf`, `cwsSdpdat`, `cwsCncdat`, `cwsCnfdat`,
`cwsAdjautodat`, `cwsLinediscmng`, `cwsExcdatdj`, `cwsTelinf`, `cwsPopuponf`,
`cwsRouteinf`, `cwsCntnslst`, `cwsDlstsinf`, `cwsAdjpicdat`, `cwsAdjchndat`,
`cwsAdjchnlist`, `cwsAdjfldlist`, `cwsAdjfvtlist`, `cwsAdjhischnlist`,
`cwsAdjregfvtchlist` (25 names, OBSERVED).

What the unit can therefore fetch (from the names and the `Cws_Apl` exports):
charging-point home/charge/manual lists and their dat, charging-point warning
and status, traffic frequency download data, route information, contents lists,
autoplay/DJ channel data, phone/telephone info, pop-up info, download-status
info, and DCM automatic information. The exact wire format of each (CSV, binary
or XML-in-XML) is **not** decoded — only the envelope is XML (section 4b).

## 6. What could be changed (for OpenCarwings work)

* **Endpoint host/path table** (section 3): built by `fn 0x000b0d58` /
  `fn 0x000b1e68` from a selector; changing a host means changing the string
  literals or the selector table — a data edit in `sec0`, not a code algorithm.
* **Request envelope** `cws_snd.xml` / `cws_rcv.xml` (section 4b): the
  application layer is XML keyed by data class; an implementer would need to
  reproduce the DLJ transport framing as well as the XML topics.
* **Bearer selection** (section 2): TCU-vs-BT-DUN-vs-APN is chosen by the DCC
  FSM and the APN table; the unit does not try every APN.

## 7. Differences between builds

* `Telema.exe` `sec0` is `0x10a7e2` (EU) vs `0x10c9fc` (US), i.e. 8730 bytes
  larger in US (`0x10c9fc − 0x10a7e2 = 0x221a`); builder VAs shift accordingly
  (e.g. CreateSession `0x000b2320` → `0x000b3474`). Module `vbase` is
  `0x00010000` in both.
* EU carries a `qa.nissan-gev.com` base-URL alternate (scheme `http://`) and a matching
  `qa.nissan-gev.com` host entry; the US run of the 18-needle scan did not find
  the QA base URL (section 3). The rest of the endpoint table is the same
  entries.
* `DCM_API.dll` is present in both builds with the same export names (EU
  `vbase=0x032c0000`, US `vbase=0x032a0000`).

## 8. Out of scope / open

* `ComMid.exe`'s message routing (it is the middleware host, but which edge
  messages it carries is not decoded).
* The binary struct layout handed to `DCC`/`DCM` (only the named fields).
* The per-data-class wire format (CSV vs binary) — the classification above is
  from names, not from a decoded record.
* No credentials, PINs, SIM IDs or VINs are copied from the binary.
