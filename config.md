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

## `cage_enabled`

Set to `true` when a holding cage is fitted to the spool. Servo 1 is the cage door the spool opens onto, servo 2 is the cage door out to the kill mechanism, and the external PIR watches the inside of the cage.

The trap arms the cage by shutting door 2 and opening door 1. Once the spool triggers it waits for the external PIR to see the animal in the cage, shuts door 1 behind it, and waits to be told what to do over UART:

- `CAGE_HOLD`: hold the animal for another `cage_hold_hours`.
- `CAGE_RELEASE`: open door 1 so the animal can get out back through the spool, which is still released. This also happens if no command comes in for `cage_hold_hours`.
- `CAGE_KILL`: open door 2 so the animal goes through to the kill mechanism.

With a door open it then waits up to `cage_exit_wait_hours` for the animal to go:

- `CAGE_WAIT`: wait another `cage_exit_wait_hours`.
- `CAGE_ESCAPED` / `CAGE_KILLED`: the animal has gone.

After that, or if nothing went into the cage, the cage is armed again and the spool reset. Nothing is saved, so if the trap restarts it forgets anything it was holding and arming the cage lets the animal out. A command sent when it doesn't apply (for example `CAGE_WAIT` while holding) gets a NACK saying why. Default: `false`

## `cage_entry_timeout_minutes`

After the spool triggers, how long to wait for the external PIR to see an animal in the cage before giving up and resetting the spool. Default: `60`

## `cage_hold_hours`

How long an animal is held in the cage before it is released, and how long a `CAGE_HOLD` extends that by (from when the command arrives). Default: `24`

## `cage_exit_wait_hours`

After a release or kill, how long to wait for the animal to leave the cage before carrying on, and how long a `CAGE_WAIT` extends that by. Default: `24`

## `program`

If the program select swithc is set to 0, the trap will instead run this program.
