# Q1: Capacity Under a Burst

## Problem Framing

The risk is not mainly whether a worker can keep 10,000 WebSockets open. The risk is that calls in flight stop meeting real-time audio deadlines while availability metrics still look fine. Each answered call is long-lived and stateful: it holds a persistent WebSocket to the speech-to-speech model and consumes CPU for audio processing, noise suppression, and VAD.

I would optimize for sustained real-time performance, not maximum connection density. A worker that accepts too many sessions may pass health checks while callers hear choppy audio because frames are late, dropped, or queued. The key capacity question is: "How many sessions can this worker sustain while preserving audio quality for existing calls?"

## Concurrency Estimate and Assumptions

The offered load is:

```text
10,000 calls / 30 minutes = 333.3 call starts per minute
333.3 / 60 = 5.56 call starts per second
```

Assumption: every outbound call is answered immediately, every call lasts exactly 40 minutes, and starts are uniformly distributed across the 30-minute launch window. Under that simplified upper bound, active concurrency rises throughout the launch period because the first calls have only been active for 30 minutes, so none have completed yet.

Under these simplifying assumptions, concurrency reaches 10,000 active sessions at minute 30. This is a conservative planning scenario for the original 10,000 calls, not a measured production peak. Actual concurrency depends on answer rates, ringing time, the call-duration distribution, retries, and the scheduling pattern.

## Measurements Needed Before Final Sizing

I would not pick a GCP machine type or calls-per-worker number from vCPU counts alone. These are the measurements I would need before final sizing:

| Measurement | How it informs design |
| --- | --- |
| CPU per active session | Measure representative audio processing with noise suppression and VAD enabled to determine safe sessions per worker. |
| Memory per active session | Measure memory at call start and across full 40-minute calls to set session density limits. |
| Audio frame processing latency | Instrument each audio stage against its real-time budget. For example, a 20 ms frame must finish within that budget, though the actual frame size may differ. |
| Late frames, underruns, drops, queue depth | These direct quality indicators should drive admission control; CPU utilization alone is not enough. |
| Answer rate and duration distribution | Use campaign and telephony data to estimate active concurrency from initiated calls. |
| Network and WebSocket behavior | Measure bandwidth, jitter, packet loss, reconnects, and stability to separate network from CPU problems. |
| Model API limits and latency | Validate provider concurrency, rate limits, quota, throttling, and response latency under load. |
| GCP instance behavior | Benchmark candidate instance families with the real audio stack; theoretical vCPU counts are not enough. |

## Architecture Approach

The scheduler should admit new calls based on safe session capacity, audio-quality metrics, provider quota, and campaign deadlines. If another call would put existing sessions at risk, it should slow or pause new starts. Existing calls are more important to protect because degraded audio is already a product failure, even if the connection is alive.

Each active call should be assigned to a stateful worker that owns the persistent model WebSocket and in-process audio pipeline for the lifetime of the call. I would not assume an active session can be migrated seamlessly. Deployments and scale-down should drain workers by letting existing calls finish while routing new calls elsewhere.

On GCP, I would use compute appropriate for long-lived CPU-bound workloads with explicit CPU and memory allocation, per-worker session limits, and reserved headroom. The platform and machine family should come from benchmarks. Whether this runs on GKE, managed instance groups, or another compute option, each worker should advertise safe session slots for the scheduler to consume.

Each worker should enforce a hard session admission limit derived from the measured audio-quality saturation point, with additional headroom for variability in speech activity and CPU scheduling. The scheduler should allocate calls only to workers with available safe session slots. Autoscaling can add capacity, but it should not override the per-worker admission limit.

Scaling should be planned ahead of the campaign. Reactive autoscaling that starts after audio quality deteriorates is too late. For a scheduled burst, I would pre-provision warm capacity for the expected peak plus redundancy.

## Real-Time Audio Quality

CPU contention can break audio without crashing the server. Audio frames arrive continuously, and noise suppression and VAD consume CPU on each stream. If too many sessions compete for CPU, frames wait in queues or are scheduled late. The process still runs, sockets stay open, and health checks pass, but the caller hears gaps, clipping, or delayed turn-taking.

I would instrument per-session audio latency, deadline misses, queue depth, underruns, dropped or late frames, end-to-end response latency, and network jitter/loss. I would separately measure model-provider latency and throttling. Local choppiness from CPU contention requires lower session density; slow model responses may require provider quota changes.

## Load Testing and Capacity Formula

First, run one representative call with real audio processing enabled and measure CPU, memory, frame latency, queue depth, and provider latency. Then increase concurrent sessions on one worker until audio quality degrades, even if connections and instance health remain normal. That point defines the unsafe region. The production limit should be below it, with headroom.

Then test the full workload shape: 40-minute duration, ramp-up, projected 10,000-call burst, varied speech activity, retries, reconnects, provider throttling, and instance failures. Long-duration tests matter because memory growth and latency tails can fail late.

I would define load-test acceptance criteria using the tail latency of audio-frame processing, deadline-miss rate, underruns, and end-to-end conversational latency. A candidate worker configuration passes only if these metrics remain within validated quality thresholds throughout the full-duration test, including peak concurrent speech activity.

The capacity calculation becomes:

```text
required workers = ceil(peak active sessions / safe sessions per worker)
```

Then add redundancy and headroom. I would not invent the safe sessions-per-worker value without measurements.

## Monitoring and Admission Control

Production scaling and admission control should use quality-aware metrics: active sessions per worker, frame processing latency, percent of frames missing deadlines, underruns, dropped frames, queue depth, CPU scheduling delay, memory usage, end-to-end response latency, WebSocket disconnects, provider throttling, and provider errors.

Audio deadline misses and queue growth should be early warning signals. When they approach validated thresholds, the scheduler should stop or reduce new call admission, allow existing sessions to continue, scale up healthy workers, and resume admission only after quality and capacity recover. The thresholds should come from benchmarked user-impact data, not arbitrary CPU percentages.

## Product and Scheduling Trade-Off

This is partly a product and scheduling problem. Starting 10,000 outbound calls in 30 minutes intentionally creates a concurrency peak. I would clarify whether the business requirement is to initiate all calls, establish all conversations, or complete the campaign within that window. If the window can be widened, the campaign may run with lower peak concurrency, lower cost, lower provider pressure, and better quality.

If the 30-minute window is mandatory, the system must be provisioned for it. Relaxing the schedule is not the only answer, but it is an important lever alongside infrastructure cost, provider capacity, call quality, and campaign deadlines.

## Engineering Summary

My approach is to quantify peak concurrency, benchmark real-time audio capacity per worker, pre-provision warm GCP capacity, admit new calls only when safe session capacity is available, and validate the design with realistic 40-minute load tests. The central principle is that existing real-time calls get protected first. A system that keeps accepting calls while degrading in-flight audio is available in the narrow sense, but it has failed the product.
