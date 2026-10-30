# Dedup: packed sample unpacking

## Context

`joulescope_ui/spectrum_engine.py` `unpack` converts packed sample data
(u1, u4) to one value per sample, and `range_tool.rsp_as_f32` now uses it
(which fixed u4 unpacking in the analysis tools).  Two more copies of the
same logic remain:

- `widgets/waveform/waveform_widget.py` (around the u1/u4 unpack in the
  sample request path)
- `widgets/trigger/trigger_widget.py` (around its u1/u4 unpack)

They also accept more dtypes than `unpack` (u16..u64, i4..i64), so they
cannot switch to it unchanged.

## Plan (do later)

1. Move `unpack` and `sample_count` from `spectrum_engine.py` to a neutral
   module, such as `joulescope_ui/samples.py`, so `range_tool.py` no
   longer depends on the spectrum engine.
2. Widen `unpack` to the dtypes the waveform and trigger widgets accept,
   with unit tests for each.
3. Replace the waveform and trigger copies with calls to it.
