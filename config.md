# User Configuration

User configuration is loaded from `config.json` on the device. The following fields are supported:

## `apir_d_threshold`

Displacement threshold for triggering the Analog PIR sensors. Default: `0.3`

## `apir_dt_threshold`

Gradient threshold for triggering the Analog PIR sensors. Default: `450`

## `max_current`

Max current in mA for the spool reset motor. Default: `1000`

## `spool_reset_delay_minutes`

After the spool has triggered it will wait this long before resetting. Default: `10`

## `latitude` / `longitude`

Position used for day and night calculations. Default: `-43.532055` / `172.636230`

## `test_loop_interval`

Loop interval in minutes. On program 9 this is how often it will loop the program. Default: `180`

## `switch_1_disable` / `switch_2_disable`

Disables the trap from triggering when a switch is in a given state. Must be one of `"IGNORE"`, `"OPEN"`, or `"CLOSED"`. Default: `"IGNORE"`

## `switch_logic`

Must be one of `"AND"` or `"OR"`. If `"OR"` then the trap will be disabled if either switch wants to disable it. If `"AND"` then both switches must want to disable it. Default: `"OR"`

**Example:** To disable the trap when a holding cage door is closed (using a reed switch that is `CLOSED` when next to a magnet): set the relevant switch to `"OPEN"`, the other to `"IGNORE"`, and `switch_logic` to `"OR"`. When the cage door closes, the switch goes from `CLOSED` to `OPEN` and the trap is disabled until the door opens again.

## `observation_mode`

In Observation Mode the trap resets at boot but does not trigger. If in a mode that reports events, it will send a `"dry-trigger"` event instead of `"triggered"`. Useful for testing AI trigger accuracy without disturbing animals. Default: `false`

## `motion_message_gap`

Minimum time in seconds between motion messages sent over UART. Default: `10`

## `post_reset_cooldown_seconds`

Seconds to wait after the spool resets before running trap checks. The reset motion can sometimes trigger motion sensors, so this delay avoids false triggers. Default: `20`

## `spool_reed_check`

Set to `true` if a reed sensor is wired up to detect when the spool is in the reset position. Default: `false`

## `manual_mode_timeout_minutes`

When a request to release or reset the spool comes in over UART the trap stops running its
sequence and goes into manual mode, where it only does what it is asked to. If no request is
made for this long it restarts itself and carries on with its sequence, so a trap is not left
disarmed. Set to `0` to stay in manual mode until the trap is restarted. Default: `30`

## `program`

If the program select swithc is set to 0, the trap will instead run this program.
