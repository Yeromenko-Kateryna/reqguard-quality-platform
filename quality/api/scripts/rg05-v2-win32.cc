// RG-05 synthetic source only. No OS backend, live authorization or settlement.
// Contract: Implementation Brief 01 sections 2, 3, 6, 9 (2026-10-18).
// Synthetic ABI extension: ScratchConfig.synthetic = { scenario: string }.
// scratchRoot is ONLY synthetic://scratch/<key>; it is never a filesystem path.
// The initial model clocks are wall=1_000_000 ms and monotonic=0 ms.
// Scenario observations advance on the first live check AFTER acquisition.
// "teardown" models environment teardown during freeze; no real resource closes.
// Model namespaces and run UUIDs are consumed until environment destruction.
// Returned evidence, including diagnostics and process identities, is synthetic.
// Nothing here attests ACLs, HANDLE custody, OS processes or supervised provenance.
#if !defined(RG05_SYNTHETIC_ONLY) || RG05_SYNTHETIC_ONLY != 1
#error Only the synthetic variant is supported
#endif
#if !defined(_WIN32) || !defined(_M_X64)
#error This source targets Windows x64 only
#endif
#if !defined(NAPI_VERSION) || NAPI_VERSION != 8
#error Build with NAPI_VERSION=8
#endif
#include <node_api.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <memory>
#include <new>
#include <regex>
#include <set>
#include <string>
#include <vector>

namespace rg05 {
constexpr uint64_t kWall = 1000000, kMax = 7200000;
const napi_type_tag kSessionTag{0x5247303553594e31ULL, 0x4c45415345524546ULL};
const napi_type_tag kProcessTag{0x5247303553594e32ULL, 0x50524f4345535352ULL};
enum class State { PREPARED, HELD, FROZEN, RELEASED };
const char* Name(State s) {
  switch (s) {
    case State::PREPARED: return "PREPARED";
    case State::HELD: return "HELD";
    case State::FROZEN: return "FROZEN";
    case State::RELEASED: return "RELEASED";
  }
  return "FROZEN";
}
struct Failure { const char* code; const char* reason; int win32 = -1; };
void Need(bool yes, const char* code = "RG05_ARGUMENT",
          const char* reason = "OS_FAILURE", int win32 = -1) {
  if (!yes) throw Failure{code, reason, win32};
}
void N(napi_status code) { Need(code == napi_ok, "RG05_INTERNAL"); }
struct Session {
  State state = State::PREPARED;
  std::string uuid, root, sid, scenario, reason, effect = "NONE";
  uint64_t expiry = 0, deadline = 0, reserve = 0;
  uint64_t wall = kWall, mono = 0, lastWall = kWall, lastMono = 0;
  bool owned = false, processOwned = false, clockInjected = false;
  unsigned attempts = 0, creates = 0, queries = 0, processQueries = 0;
  unsigned closes = 0, processCloses = 0;
  std::vector<std::string> trace{"prepare"};
};
struct Process { Session* session; };
struct Env {
  napi_ref descriptor = nullptr;
  std::vector<napi_ref> roots;
  std::vector<std::unique_ptr<Session>> sessions;
  std::vector<std::unique_ptr<Process>> processes;
  std::set<std::string> consumedRoots;
  // Registration tombstones have fixed storage: consuming a validated UUID
  // cannot allocate, and no failed registration ever removes its tombstone.
  using RunKey = std::array<char, 36>;
  std::array<RunKey, 256> consumedRuns{};
  size_t consumedRunCount = 0;
  bool inCall = false;
};
void Frozen(Session* s, const char* reason) noexcept {
  if (s && s->state != State::RELEASED && s->state != State::FROZEN) {
    s->state = State::FROZEN;
    // Preserve fail-closed state even if string allocation fails.
    try { s->reason = reason; } catch (...) {}
  }
}
void Teardown(Session& s) noexcept {
  Frozen(&s, "CALLER_STOP");
  if (s.owned) { s.owned = false; ++s.closes; }
  if (s.processOwned) { s.processOwned = false; ++s.processCloses; }
  s.state = State::RELEASED;
}
void Cleanup(napi_env env, void* data, void*) noexcept {
  auto* e = static_cast<Env*>(data);
  for (auto& s : e->sessions) Teardown(*s);
  for (auto ref : e->roots) napi_delete_reference(env, ref);
  if (e->descriptor) napi_delete_reference(env, e->descriptor);
  delete e;
}
napi_valuetype Type(napi_env e, napi_value v) {
  napi_valuetype t; N(napi_typeof(e, v, &t)); return t;
}
napi_value Str(napi_env e, const std::string& s) {
  napi_value v; N(napi_create_string_utf8(e, s.data(), s.size(), &v)); return v;
}
napi_value Num(napi_env e, uint32_t x) {
  napi_value v; N(napi_create_uint32(e, x, &v)); return v;
}
napi_value Big(napi_env e, uint64_t x) {
  napi_value v; N(napi_create_bigint_uint64(e, x, &v)); return v;
}
napi_value Bool(napi_env e, bool x) {
  napi_value v; N(napi_get_boolean(e, x, &v)); return v;
}
napi_value Null(napi_env e) { napi_value v; N(napi_get_null(e, &v)); return v; }
bool IsObject(napi_env e, napi_value v) {
  if (Type(e, v) != napi_object) return false;
  bool isNull; N(napi_strict_equals(e, v, Null(e), &isNull)); return !isNull;
}
napi_value Obj(napi_env e) { napi_value v; N(napi_create_object(e, &v)); return v; }
void Put(napi_env e, napi_value o, const char* key, napi_value v) {
  // Define own data properties; never invoke an inherited setter.
  napi_property_descriptor p{key, nullptr, nullptr, nullptr, nullptr, v,
                            napi_enumerable, nullptr};
  N(napi_define_properties(e, o, 1, &p));
}
napi_value Seal(napi_env e, napi_value o) { N(napi_object_freeze(e, o)); return o; }
std::string String(napi_env e, napi_value v, size_t limit = 160) {
  Need(Type(e, v) == napi_string);
  size_t n; N(napi_get_value_string_utf8(e, v, nullptr, 0, &n));
  Need(n > 0 && n <= limit);
  std::vector<char> bytes(n + 1);
  size_t copied; N(napi_get_value_string_utf8(e, v, bytes.data(), bytes.size(), &copied));
  Need(copied == n);
  std::string result(bytes.data(), n);
  Need(result.find('\0') == std::string::npos);
  return result;
}
uint64_t Integer(napi_env e, napi_value v, uint64_t limit = kMax) {
  Need(Type(e, v) == napi_bigint);
  uint64_t x; bool lossless;
  N(napi_get_value_bigint_uint64(e, v, &x, &lossless));
  Need(lossless && x <= limit); return x;
}
uint32_t Number(napi_env e, napi_value v) {
  Need(Type(e, v) == napi_number);
  double x; N(napi_get_value_double(e, v, &x));
  Need(std::isfinite(x) && x >= 1 && x <= 4294967295.0 && std::floor(x) == x);
  return static_cast<uint32_t>(x);
}
bool Matches(const std::string& s, const char* pattern) {
  return std::regex_match(s, std::regex(pattern));
}
// Reflect only own descriptors, then COPY values. Accessors are never invoked.
// Descriptor/proxy traps may execute JS; reentry is refused by Call's guard.
napi_value Field(napi_env e, Env& d, napi_value o, const char* key) {
  napi_value fn, global, desc;
  N(napi_get_reference_value(e, d.descriptor, &fn));
  N(napi_get_global(e, &global));
  napi_value args[]{o, Str(e, key)};
  N(napi_call_function(e, global, fn, 2, args, &desc));
  Need(IsObject(e, desc));
  bool own = false; N(napi_has_own_property(e, desc, Str(e, "value"), &own));
  Need(own);
  napi_value v; N(napi_get_named_property(e, desc, "value", &v)); return v;
}
void Fields(napi_env e, napi_value o, std::initializer_list<const char*> names) {
  Need(IsObject(e, o));
  bool array; N(napi_is_array(e, o, &array)); Need(!array);
  napi_value keys;
  N(napi_get_all_property_names(e, o, napi_key_own_only, napi_key_all_properties,
                                napi_key_numbers_to_strings, &keys));
  uint32_t count; N(napi_get_array_length(e, keys, &count)); Need(count == names.size());
  for (uint32_t i = 0; i < count; ++i) {
    napi_value v; N(napi_get_element(e, keys, i, &v));
    auto key = String(e, v);
    Need(std::any_of(names.begin(), names.end(), [&](const char* n) { return key == n; }));
  }
}
Session* SessionOf(napi_env e, Env& d, napi_value v) {
  if (!IsObject(e, v)) return nullptr;
  bool tagged = false; N(napi_check_object_type_tag(e, v, &kSessionTag, &tagged));
  if (!tagged) return nullptr;
  void* p = nullptr; N(napi_unwrap(e, v, &p));
  for (const auto& s : d.sessions) if (s.get() == p) return s.get();
  return nullptr;
}
Process* ProcessOf(napi_env e, Env& d, napi_value v, Session* owner) {
  Need(IsObject(e, v));
  bool tagged = false; N(napi_check_object_type_tag(e, v, &kProcessTag, &tagged));
  Need(tagged);
  void* p = nullptr; N(napi_unwrap(e, v, &p));
  for (const auto& ref : d.processes) if (ref.get() == p) {
    Need(ref->session == owner, "RG05_IDENTITY", "IDENTITY_MISMATCH"); return ref.get();
  }
  throw Failure{"RG05_ARGUMENT", "IDENTITY_MISMATCH"};
}
napi_value Opaque(napi_env e, Env& d, void* ptr, const napi_type_tag& tag) {
  napi_value o = Obj(e);
  N(napi_type_tag_object(e, o, &tag));
  N(napi_wrap(e, o, ptr, nullptr, nullptr, nullptr));
  napi_ref ref; N(napi_create_reference(e, o, 1, &ref));
  try { d.roots.push_back(ref); } catch (...) { napi_delete_reference(e, ref); throw; }
  return Seal(e, o); // Lifetime belongs to Env, never to a GC finalizer.
}
napi_value File(napi_env e) {
  auto o = Obj(e);
  Put(e, o, "evidence", Str(e, "synthetic"));
  Put(e, o, "volumeSerialHex", Str(e, "0000000000000001"));
  Put(e, o, "fileIdHex", Str(e, "00000000000000000000000000000001"));
  return Seal(e, o);
}
napi_value Identity(napi_env e, const Session& s) {
  auto o = Obj(e);
  Put(e, o, "evidence", Str(e, "synthetic"));
  Put(e, o, "pid", Num(e, 7)); Put(e, o, "creationTime100ns", Big(e, 1));
  Put(e, o, "executablePath", Str(e, "synthetic://process/fixture"));
  Put(e, o, "executableSha256", Str(e, std::string(64, 'a')));
  Put(e, o, "tokenUserSid", Str(e, s.sid)); return Seal(e, o);
}
uint64_t Remaining(const Session& s) {
  if (s.wall >= s.expiry || s.mono >= s.deadline) return 0;
  return std::min(s.expiry - s.wall, s.deadline - s.mono);
}
void Live(Session& s, uint64_t work) {
  Need(s.state == State::HELD, "RG05_STATE");
  s.trace.push_back("clock.check");
  if (!s.clockInjected) {
    s.clockInjected = true;
    if (s.scenario == "wall-expiry") s.wall = s.expiry;
    if (s.scenario == "mono-expiry") s.mono = s.deadline;
    if (s.scenario == "wall-regression") s.wall = kWall - 1;
    if (s.scenario == "mono-regression") { s.lastMono = 1; s.mono = 0; }
    Need(s.scenario != "clock-failure", "RG05_OS", "CLOCK_UNCERTAIN", 13);
  }
  Need(s.wall >= s.lastWall && s.mono >= s.lastMono, "RG05_EXPIRED", "CLOCK_UNCERTAIN");
  s.lastWall = s.wall; s.lastMono = s.mono;
  Need(Remaining(s) > 0, "RG05_EXPIRED", "EXPIRED");
  Need(Remaining(s) > work + s.reserve, "RG05_BUDGET", "BUDGET_INSUFFICIENT");
  ++s.queries; s.trace.push_back("lease.query");
  Need(s.scenario != "invalidated", "RG05_OS", "OS_FAILURE", 6);
  for (const auto* drift : {"file-drift", "volume-drift", "parent-drift", "sid-drift", "acl-drift"})
    Need(s.scenario != drift, "RG05_IDENTITY", "IDENTITY_MISMATCH");
}
napi_value Audit(napi_env e, const Session& s) {
  auto o = Obj(e);
  Put(e, o, "evidence", Str(e, "synthetic"));
  Put(e, o, "realOperations", Num(e, 0)); Put(e, o, "createAttempts", Num(e, s.attempts));
  Put(e, o, "modelCreates", Num(e, s.creates)); Put(e, o, "leaseQueries", Num(e, s.queries));
  Put(e, o, "processQueries", Num(e, s.processQueries));
  Put(e, o, "modelCloses", Num(e, s.closes)); Put(e, o, "modelProcessCloses", Num(e, s.processCloses));
  Put(e, o, "deletes", Num(e, 0)); Put(e, o, "reopens", Num(e, 0));
  Put(e, o, "duplicates", Num(e, 0));
  napi_value trace; N(napi_create_array_with_length(e, s.trace.size(), &trace));
  for (uint32_t i = 0; i < s.trace.size(); ++i) N(napi_set_element(e, trace, i, Str(e, s.trace[i])));
  Put(e, o, "trace", Seal(e, trace)); return Seal(e, o);
}
napi_value Status(napi_env e, const Session& s) {
  auto o = Obj(e);
  Put(e, o, "evidence", Str(e, "synthetic")); Put(e, o, "state", Str(e, Name(s.state)));
  Put(e, o, "reason", s.reason.empty() ? Null(e) : Str(e, s.reason));
  Put(e, o, "lock", s.creates ? File(e) : Null(e));
  Put(e, o, "remainingMs", Big(e, s.state == State::HELD ? Remaining(s) : 0));
  Put(e, o, "admissionSupported", Bool(e, false)); Put(e, o, "audit", Audit(e, s));
  return Seal(e, o);
}
napi_value Lease(napi_env e, const Session& s) {
  auto o = Obj(e);
  Put(e, o, "evidence", Str(e, "synthetic")); Put(e, o, "state", Str(e, "HELD"));
  Put(e, o, "runUuid", Str(e, s.uuid)); Put(e, o, "lock", File(e));
  Put(e, o, "owner", Identity(e, s)); Put(e, o, "remainingMs", Big(e, Remaining(s)));
  Put(e, o, "admissionSupported", Bool(e, false)); return Seal(e, o);
}
const std::set<std::string> kScenarios{
  "success", "collision-exists", "collision-already", "collision-sharing", "stale",
  "null-handle", "invalid-handle", "post-create-query", "uncertain-create", "inheritance",
  "file-drift", "volume-drift", "parent-drift", "sid-drift", "acl-drift", "invalidated",
  "pid-reuse", "process-exit", "pid-reuse-after-observe", "process-exit-after-observe",
  "process-query", "process-wait", "wall-expiry", "mono-expiry",
  "wall-regression", "mono-regression", "clock-failure", "teardown", "registration-failure"
};
Session* Prepare(napi_env e, Env& d, napi_value config) {
  Fields(e, config, {"schema", "runUuid", "scratchRoot", "trustedRunnerSid",
                    "expiresAtUnixMs", "maxLifetimeMs", "settlementReserveMs", "synthetic"});
  auto f = [&](const char* key) { return Field(e, d, config, key); };
  Need(Number(e, f("schema")) == 1);
  auto s = std::make_unique<Session>();
  s->uuid = String(e, f("runUuid"));
  Need(Matches(s->uuid, "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"));
  s->root = String(e, f("scratchRoot"), 512);
  Need(Matches(s->root, "synthetic://scratch/[a-z0-9-]{1,64}"), "RG05_PATH_DENIED");
  s->sid = String(e, f("trustedRunnerSid"));
  // A single explicit, bounded synthetic SID fixture, never an effective OS SID.
  Need(s->sid == "S-1-5-21-1-2-3-1001");
  auto synthetic = f("synthetic"); Fields(e, synthetic, {"scenario"});
  s->scenario = String(e, Field(e, d, synthetic, "scenario"));
  Need(kScenarios.count(s->scenario) == 1);
  auto max = Integer(e, f("maxLifetimeMs")); Need(max > 0);
  s->expiry = Integer(e, f("expiresAtUnixMs"), kWall + kMax);
  Need(s->expiry > kWall && s->expiry - kWall <= max);
  s->deadline = s->expiry - kWall;
  s->reserve = Integer(e, f("settlementReserveMs"));
  Need(s->reserve > 0 && s->reserve < s->deadline);
  Need(d.consumedRunCount < d.consumedRuns.size(), "RG05_STATE");
  Env::RunKey key{}; // The validated canonical UUID is exactly 36 bytes.
  std::copy(s->uuid.begin(), s->uuid.end(), key.begin());
  for (size_t i = 0; i < d.consumedRunCount; ++i)
    Need(d.consumedRuns[i] != key, "RG05_STATE");
  // Non-allocating commit, BEFORE the potentially allocating vector insertion.
  d.consumedRuns[d.consumedRunCount++] = key;
  // Deterministically model allocation failure at the registration boundary.
  // The local unique_ptr is reclaimed, but the UUID remains consumed.
  if (s->scenario == "registration-failure") throw std::bad_alloc{};
  auto* result = s.get();
  d.sessions.push_back(std::move(s)); // noexcept unique_ptr move; no rollback of UUID.
  return result;
}
void Acquire(Env& d, Session& s) {
  Need(s.state == State::PREPARED && s.attempts == 0, "RG05_STATE");
  // No clock scenario is injected until after this initial acquisition check.
  Need(Remaining(s) > s.reserve, "RG05_BUDGET", "BUDGET_INSUFFICIENT");
  ++s.attempts; s.trace.push_back("create.attempt");
  int collision = s.scenario == "collision-already" ? 183 :
                  s.scenario == "collision-sharing" ? 32 : 80;
  if (s.scenario == "collision-exists" || s.scenario == "collision-already" ||
      s.scenario == "collision-sharing" || s.scenario == "stale")
    d.consumedRoots.insert(s.root); // A fixture collision also persists across sessions.
  Need(s.scenario != "collision-exists" && s.scenario != "collision-already" &&
       s.scenario != "collision-sharing" && s.scenario != "stale" &&
       d.consumedRoots.count(s.root) == 0, "RG05_COLLISION", "OS_FAILURE", collision);
  // Consumed before any modeled result; uncertain/invalid outcomes cannot retry.
  d.consumedRoots.insert(s.root);
  s.effect = "UNKNOWN";
  Need(s.scenario != "uncertain-create", "RG05_OS", "OS_FAILURE", 995);
  Need(s.scenario != "null-handle" && s.scenario != "invalid-handle", "RG05_OS", "OS_FAILURE", 6);
  ++s.creates; s.owned = true; s.effect = "CREATED";
  s.trace.push_back("create.success");
  ++s.queries; s.trace.push_back("identity.query");
  Need(s.scenario != "post-create-query", "RG05_OS", "OS_FAILURE", 5);
  s.trace.push_back("inheritance.check");
  Need(s.scenario != "inheritance", "RG05_IDENTITY", "IDENTITY_MISMATCH");
  s.state = State::HELD; s.trace.push_back("held");
}
void Expected(napi_env e, Env& d, Session& s, uint32_t pid, napi_value value) {
  Fields(e, value, {"pid", "creationTime100ns", "executablePath", "executableSha256", "tokenUserSid"});
  auto f = [&](const char* key) { return Field(e, d, value, key); };
  auto expectedPid = Number(e, f("pid"));
  auto time = Integer(e, f("creationTime100ns"), UINT64_MAX);
  auto path = String(e, f("executablePath"));
  auto hash = String(e, f("executableSha256"));
  auto sid = String(e, f("tokenUserSid"));
  Need(Matches(hash, "[0-9a-f]{64}"));
  Need(Matches(sid, "S-1-[0-9]{1,15}(-[0-9]{1,10}){1,15}"));
  Need(pid == 7 && expectedPid == pid && time == 1 && path == "synthetic://process/fixture" &&
       hash == std::string(64, 'a') && sid == s.sid, "RG05_IDENTITY", "IDENTITY_MISMATCH");
}
void CheckProcess(Session& s) {
  ++s.processQueries; s.trace.push_back("process.query");
  Need(s.scenario != "process-query", "RG05_OS", "OS_FAILURE", 5);
  s.trace.push_back("process.wait");
  Need(s.scenario != "process-wait", "RG05_OS", "OS_FAILURE", 6);
  Need(s.scenario != "pid-reuse" && s.scenario != "process-exit", "RG05_IDENTITY", "IDENTITY_MISMATCH");
  Need(s.processQueries < 2 || (s.scenario != "pid-reuse-after-observe" &&
       s.scenario != "process-exit-after-observe"), "RG05_IDENTITY", "IDENTITY_MISMATCH");
}
enum class Op { Info, Prepare, Acquire, CheckLease, Observe, CheckProcess, Freeze, Status };
const char* OpName(Op op) {
  switch (op) {
    case Op::Info: return "bridgeInfo"; case Op::Prepare: return "prepareScratch";
    case Op::Acquire: return "acquireScratchLease"; case Op::CheckLease: return "checkLease";
    case Op::Observe: return "observeProcess"; case Op::CheckProcess: return "checkProcess";
    case Op::Freeze: return "freeze"; case Op::Status: return "status";
  }
  return "bridge";
}
struct Binding { Op op; size_t argc; };
Binding bindings[]{{Op::Info, 0}, {Op::Prepare, 1}, {Op::Acquire, 1}, {Op::CheckLease, 2},
                   {Op::Observe, 3}, {Op::CheckProcess, 2}, {Op::Freeze, 2}, {Op::Status, 1}};
void Error(napi_env e, const Failure& f, const char* op, Session* s) noexcept {
  bool pending = false;
  if (napi_is_exception_pending(e, &pending) != napi_ok || pending) return;
  try {
    napi_value error; N(napi_create_error(e, nullptr, Str(e, "RG05 synthetic operation refused"), &error));
    Put(e, error, "code", Str(e, f.code)); Put(e, error, "operation", Str(e, op));
    Put(e, error, "evidence", Str(e, "synthetic"));
    Put(e, error, "win32Code", f.win32 < 0 ? Null(e) : Num(e, static_cast<uint32_t>(f.win32)));
    Put(e, error, "state", s ? Str(e, Name(s->state)) : Null(e));
    Put(e, error, "effect", Str(e, s ? s->effect : "NONE"));
    N(napi_throw(e, Seal(e, error)));
  } catch (...) {
    if (napi_is_exception_pending(e, &pending) == napi_ok && !pending)
      napi_throw_error(e, "RG05_INTERNAL", "RG05 synthetic operation refused");
  }
}
napi_value Call(napi_env e, napi_callback_info info) noexcept {
  Session* s = nullptr; Env* d = nullptr; Binding* b = nullptr; bool entered = false;
  try {
    void* data = nullptr; size_t count = 4; napi_value args[4]{};
    N(napi_get_cb_info(e, info, &count, args, nullptr, &data));
    b = static_cast<Binding*>(data);
    void* instance = nullptr; N(napi_get_instance_data(e, &instance)); d = static_cast<Env*>(instance);
    Need(d != nullptr, "RG05_INTERNAL");
    if (count && b->op != Op::Prepare && b->op != Op::Info) s = SessionOf(e, *d, args[0]);
    Need(!d->inCall, "RG05_STATE"); d->inCall = true; entered = true;
    struct Guard { Env* d; ~Guard() { d->inCall = false; } } guard{d};
    Need(count == b->argc);
    if (b->op == Op::Info) {
      auto o = Obj(e); Put(e, o, "abi", Num(e, 1)); Put(e, o, "napiVersion", Num(e, 8));
      Put(e, o, "platform", Str(e, "win32")); Put(e, o, "architecture", Str(e, "x64"));
      Put(e, o, "admissionSupported", Bool(e, false)); Put(e, o, "dispatchSupported", Bool(e, false));
      Put(e, o, "evidence", Str(e, "synthetic")); return Seal(e, o);
    }
    if (b->op == Op::Prepare) {
      s = Prepare(e, *d, args[0]); return Opaque(e, *d, s, kSessionTag);
    }
    Need(s != nullptr);
    switch (b->op) {
      case Op::Acquire: Acquire(*d, *s); return Lease(e, *s);
      case Op::CheckLease: Live(*s, Integer(e, args[1])); return Lease(e, *s);
      case Op::Observe: {
        auto pid = Number(e, args[1]); Expected(e, *d, *s, pid, args[2]); Live(*s, 0);
        Need(!s->processOwned, "RG05_STATE");
        // Model an opened process object even if a later observation fails.
        s->processOwned = true; CheckProcess(*s);
        auto p = std::make_unique<Process>(); p->session = s;
        auto* ptr = p.get(); d->processes.push_back(std::move(p));
        return Opaque(e, *d, ptr, kProcessTag);
      }
      case Op::CheckProcess:
        ProcessOf(e, *d, args[1], s); Live(*s, 0); CheckProcess(*s); return Identity(e, *s);
      case Op::Freeze:
        Need(String(e, args[1]) == "CALLER_STOP");
        Frozen(s, "CALLER_STOP");
        if (s->scenario == "teardown") {
          s->trace.push_back("freeze"); Teardown(*s); s->trace.push_back("teardown");
        }
        return Status(e, *s);
      case Op::Status: return Status(e, *s); // Diagnostic only; no injected clocks.
      default: throw Failure{"RG05_INTERNAL", "OS_FAILURE"};
    }
  } catch (const Failure& f) {
    if (!b || b->op != Op::Status) Frozen(s, f.reason);
    Error(e, f, b ? OpName(b->op) : "bridge", s);
  } catch (...) {
    Frozen(s, "OS_FAILURE");
    Error(e, Failure{"RG05_INTERNAL", "OS_FAILURE"}, b ? OpName(b->op) : "bridge", s);
  }
  // A nested call must not clear the outer guard.
  if (entered && d) d->inCall = false;
  return nullptr;
}
napi_value Init(napi_env e, napi_value exports) noexcept {
  std::unique_ptr<Env> data;
  try {
    data = std::make_unique<Env>();
    napi_value global, object, descriptor;
    N(napi_get_global(e, &global)); N(napi_get_named_property(e, global, "Object", &object));
    N(napi_get_named_property(e, object, "getOwnPropertyDescriptor", &descriptor));
    Need(Type(e, descriptor) == napi_function, "RG05_INTERNAL");
    N(napi_create_reference(e, descriptor, 1, &data->descriptor));
    N(napi_set_instance_data(e, data.get(), Cleanup, nullptr));
    data.release();
    for (auto& b : bindings) {
      napi_property_descriptor p{OpName(b.op), nullptr, Call, nullptr, nullptr, nullptr,
                                napi_enumerable, &b};
      N(napi_define_properties(e, exports, 1, &p));
    }
    return Seal(e, exports);
  } catch (...) {
    // Before installation, reclaim the reference too; afterwards Node owns Env.
    if (data && data->descriptor) napi_delete_reference(e, data->descriptor);
    Error(e, Failure{"RG05_INTERNAL", "OS_FAILURE"}, "initialize", nullptr);
    return nullptr;
  }
}
} // namespace rg05
NAPI_MODULE(rg05_v2_win32, rg05::Init)
