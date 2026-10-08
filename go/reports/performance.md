# Phase 2 paired performance measurements

5 trials × 3 iterations; untimed warmup. Speedup = Python / Go.

| Scope | Case | N / FFT | Python median ms (p90) | Go median ms (p90) | Speedup | Python / Go MSamples/s | Go B/op / allocs/op |
|---|---|---|---|---|---|---|---|
| Core | complex_999_all | 999 / 999 | 0.0718 (0.0816) | 0.0556 (0.0582) | 1.292 | 13.920 / 17.978 | 106496 / 8 |
| E2E | complex_999_all | 999 / 999 | 4.8152 (4.9300) | 0.2702 (0.2750) | 17.819 | 0.207 / 3.697 | 235034 / 1071 |
| CSV | complex_999_all | 999 / 999 | 4.5850 (4.7167) | 0.2221 (0.2444) | 20.641 | 0.218 / 4.497 | 128538 / 1063 |
| Core | complex_333_all | 333 / 333 | 0.0539 (0.0659) | 0.0183 (0.0192) | 2.938 | 6.182 / 18.164 | 35072 / 8 |
| E2E | complex_333_all | 333 / 333 | 3.2253 (3.3576) | 0.1405 (0.1475) | 22.956 | 0.103 / 2.370 | 97594 / 403 |
| CSV | complex_333_all | 333 / 333 | 2.9912 (3.2873) | 0.1149 (0.1255) | 26.026 | 0.111 / 2.897 | 62522 / 395 |
| Core | complex_1024_all | 1024 / 1024 | 0.0627 (0.0702) | 0.0412 (0.0451) | 1.521 | 16.323 / 24.834 | 106496 / 8 |
| E2E | complex_1024_all | 1024 / 1024 | 4.5276 (4.6171) | 0.2640 (0.2820) | 17.150 | 0.226 / 3.879 | 236250 / 1096 |
| CSV | complex_1024_all | 1024 / 1024 | 4.4301 (4.5732) | 0.2239 (0.2365) | 19.786 | 0.231 / 4.573 | 129754 / 1088 |
| Core | complex_8192_all | 8192 / 8192 | 0.2279 (0.3779) | 0.3997 (0.4629) | 0.570 | 35.940 / 20.495 | 851968 / 8 |
| E2E | complex_8192_all | 8192 / 8192 | 19.8010 (20.3763) | 1.8551 (1.9500) | 10.674 | 0.414 / 4.416 | 1780442 / 8270 |
| CSV | complex_8192_all | 8192 / 8192 | 20.4713 (22.8228) | 1.4054 (1.4171) | 14.567 | 0.400 / 5.829 | 928474 / 8262 |
| Core | complex_8192_welch1024 | 8192 / 1024 | 0.4831 (0.6997) | 0.2036 (0.2138) | 2.373 | 16.958 / 40.236 | 106496 / 8 |
| E2E | complex_8192_welch1024 | 8192 / 1024 | 21.7472 (30.4908) | 1.7260 (1.7707) | 12.600 | 0.377 / 4.746 | 1034970 / 8270 |
| Core | complex_65536_all | 65536 / 65536 | 4.8548 (5.3898) | 3.5837 (3.8262) | 1.355 | 13.499 / 18.287 | 6815744 / 8 |
| E2E | complex_65536_all | 65536 / 65536 | 145.5918 (151.8970) | 14.8771 (15.0728) | 9.786 | 0.450 / 4.405 | 15553386 / 65625 |
| CSV | complex_65536_all | 65536 / 65536 | 135.8191 (137.9766) | 11.0217 (11.2293) | 12.323 | 0.483 / 5.946 | 8736536 / 65616 |
| Core | complex_65536_welch1024 | 65536 / 1024 | 1.5482 (1.6934) | 1.4991 (1.5542) | 1.033 | 42.330 / 43.716 | 106496 / 8 |
| E2E | complex_65536_welch1024 | 65536 / 1024 | 141.6377 (144.0509) | 12.5591 (12.7360) | 11.278 | 0.463 / 5.218 | 8843032 / 65624 |
| Core | complex_1048576_all | 1048576 / 1048576 | 95.8345 (96.9942) | 72.2662 (74.2768) | 1.326 | 10.942 / 14.510 | 109051904 / 8 |
| E2E | complex_1048576_all | 1048576 / 1048576 | 2903.9685 (3005.8078) | 256.4649 (260.1780) | 11.323 | 0.361 / 4.089 | 247456949 / 1048683 |
| CSV | complex_1048576_all | 1048576 / 1048576 | 2812.4468 (2839.9753) | 178.4244 (181.9977) | 15.763 | 0.373 / 5.877 | 138405088 / 1048675 |
| Core | complex_1048576_welch1024 | 1048576 / 1024 | 25.8597 (26.1947) | 26.3365 (27.0879) | 0.982 | 40.549 / 39.815 | 106496 / 8 |
| E2E | complex_1048576_welch1024 | 1048576 / 1024 | 2767.0966 (2781.3972) | 205.5027 (209.2731) | 13.465 | 0.379 / 5.102 | 138514749 / 1048685 |
| Core | real_8192_all | 8192 / 8192 | 0.1941 (0.2154) | 0.2957 (0.3132) | 0.657 | 42.198 / 27.704 | 565248 / 9 |
| E2E | real_8192_all | 8192 / 8192 | 18.4054 (18.4549) | 1.1512 (1.2382) | 15.988 | 0.445 / 7.116 | 1051208 / 8267 |
| CSV | real_8192_all | 8192 / 8192 | 18.0130 (20.2950) | 0.9172 (0.9584) | 19.638 | 0.455 / 8.931 | 485960 / 8258 |
| Core | real_8192_welch1024 | 8192 / 1024 | 0.2016 (0.2077) | 0.1879 (0.2809) | 1.073 | 40.628 / 43.598 | 69888 / 9 |
| E2E | real_8192_welch1024 | 8192 / 1024 | 17.9622 (18.7335) | 0.9539 (0.9696) | 18.830 | 0.456 / 8.588 | 555848 / 8267 |
| Core | real_65536_all | 65536 / 65536 | 3.1304 (3.3009) | 2.5773 (2.6222) | 1.215 | 20.935 / 25.428 | 4235264 / 9 |
| E2E | real_65536_all | 65536 / 65536 | 91.3009 (92.0247) | 7.7961 (8.8175) | 11.711 | 0.718 / 8.406 | 8352282 / 65622 |
| CSV | real_65536_all | 65536 / 65536 | 88.4565 (91.2318) | 5.8337 (5.9948) | 15.163 | 0.741 / 11.234 | 4114792 / 65610 |
| Core | real_65536_welch1024 | 65536 / 1024 | 1.4493 (1.5462) | 1.4061 (1.4244) | 1.031 | 45.218 / 46.608 | 69888 / 9 |
| E2E | real_65536_welch1024 | 65536 / 1024 | 87.5092 (90.7084) | 6.8082 (7.1884) | 12.853 | 0.749 / 9.626 | 4184765 / 65620 |

Core includes input validation, window construction, FFT plan/setup, FFT, PSD, normalization and result allocation. Welch reuses its plan within each call.
CSV includes file open/read and decode; E2E includes file decode plus PSD. Compilation, process launch, fixture generation, plots and JSON are excluded.
Shared CSV fixtures use 17-digit float roundtrip; both core measurements consume decoded identical samples. Fixed seed 20261008.
CSV runs use a warm filesystem cache; this is not a cold-storage benchmark. Runs are sequential without affinity, process isolation or forced power policy.
Go allocated B/op and allocs/op are not peak RSS; uniform peak RSS and Python native allocations are NOT MEASURED.
Go and Python repeat methods use per-trial mean timing; median/p90 summarize trials, not individual-call latency.
Python timings are retained from the paired baseline; Go was rerun after buffer reuse with identical shared fixtures and iteration settings.
