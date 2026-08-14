# Microcontroller code

## Upload for the arms

Be sure to have `pio` (the Platformio core CLI)

```sh
just upload
```

## Upload for the Motors

```sh
PIO_ENV=Motor just upload
```

## Set up your development environment

Read [this README](./platformio-core.README.md)

## Test the 67

```sh
PIO_ENV=Arms67 just upload
```
