# spool-py

This is the micropython code to be run on a spool PCB.

## Uploading code

mpremote is required to use these helper scripts to upload the code to the PCB.

Use `./upload` to upload code to a spool.

## Running and Testing code

Use `./run <src/file.py>` to upload all files and then run the target file.
The `--skip-update` option will skip the upload step and just run the file.

## Programs

There is a rotary switch on the PCB to select different programs.

If the program uses the UART then it can commands can be sent though UART to update the software/time and other such commands.

## Status

The camera can ask the trap what it is doing with a `STATUS` message. The trap answers straight away with a `STATUS_R` message. The trap also sends the status on its own, as a `STATUS_CHANGED` message, whenever it changes, or the camera's ENABLE runs out (checked every 100 ms, so changes close together are sent as one). Both payloads are JSON with:

- `State`: what the trap sequence is doing. `RESETTING` (arming the cage, if there is one, and resetting the spool), `RESET_FAILED` (the reed switch showed the spool didn't stay reset, see `spool_reed_check`), `ARMED` (waiting for motion), `TRIGGERED` (waiting `spool_reset_delay_minutes` to reset), `CAGE` (running the cage sequence) or `MANUAL` (in manual mode). Programs that don't run the trap sequence leave it out.
- `Enabled` and `DisabledReason`: while `ARMED`, whether the enable checks pass and, if not, why.
- `Request`: in manual mode, the request being run, such as `OPEN_DOOR_1`.
- `CagePhase`: with a cage (`cage_doors`), the cage phase: `IDLE`, `WAITING_FOR_ENTRY`, `MOVING`, `HOLDING`, `EXITING` or `MANUAL`.
- `CameraEnabled`: for programs the camera enables, whether the camera's last ENABLE is still in force.

## Events

When the trap communicates with the camera it can send though messages that the camera will turn into events. These are:

- trapMotion: Each time the trap detects motion it will report this, limited to one every 30 seconds. This is intended to help with seeing how the trap might be over/under triggering.
- trapEnabled: The trap was disabled but it is now enabled.
- trapDisabled: The trap is disabled, a new message will be sent every time the disabled reason changes
- trapEnableCommand: The trap has had a message from the camera that it can be enable. Note that the trap might still be disabled for other reasons (daytime, cage switch). An ENABLE only lasts for the number of seconds in its payload (300 if there isn't one), so the camera keeps sending it while it wants the trap enabled. If the camera stops, for example because it has powered off or been unplugged, the trap disables itself with the reason "Camera stopped enabling the trap".
- trapDisableCommand: The trap has had a message from the camera to disable it.
- trapError: This catches a couple different types of errors.
  - error-code: An recognised error has happened. This will also make the trap beep.
  - runtime-error: An python runtime error occurred.
- trapTriggered: The trap has just triggered.
- trapSpoolReset: The spool on the trap was reset
- trapSpoolResetFailed: With `spool_reed_check` set, the reed switch showed that the spool didn't stay reset. The trap doesn't try again, so it can't trigger until it is asked to reset the spool (a manual RESET_SPOOL) or is restarted. `Reason` says what went wrong.
- trapRunning: The program that is running on the trap.
- trapRtcBatteryFlat: The trap started with its RTC showing it lost power, because the RTC battery is flat. The time is wrong until the camera sets it, which it does once its own clock has synced. Until then night only mode counts it as night, so the trap stays active.
- Cage events, when a cage is fitted (`cage_doors`, see config.md):
  - trapCageNoEntry: The spool triggered but nothing was seen going into the cage.
  - trapCageCaptured: An animal has been shut in the cage. `HoldHours` is how long until it is released.
  - trapCageHolding: A hold command extended the hold by `HoldHours`.
  - trapCageReleasing: The spool side door is opening to let the animal go. `Reason` is `command` or `timeout`.
  - trapCageKilling: The door to the kill mechanism is opening.
  - trapCageWaiting: A wait command extended the wait for the animal to leave by `WaitHours`.
  - trapCageFinished: The animal has left the cage. `Action` is `RELEASE` or `KILL`, `Result` is `ESCAPED`, `KILLED` or `TIMEOUT`.
