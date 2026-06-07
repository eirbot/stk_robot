# Raspberry code with ROS Jazzy 

Powered by: Pixi + Robostack (ROS Jazzy)

## Install dev environment

Requirements:

- devenv.sh

Enter in the development virtual super-environment with either allowing all the
shells to automatically source it each time you enter in the working directory:

```sh
devenv allow
```

Or exceptionally enter into it with this commmand

```sh
devenv shell
```

Once in your virtual super-environment, install the jazzy distribution with this
script command

```sh
ros-install
```

## Run some ROS scripts

TODO: use the scripts sourced by the `devenv` environment.

## Add some ROS packages

In the virtual super-environment, search the available packages on the
`robostack-jazzy` package channel [(referenced here)](https://robostack.github.io/jazzy.html) or with the `pixi` cli:

```sh
pixi search 'ros-jazzy-*'
```

To add a package

```sh
pixi add 'ros-jazzy-easynav' # not sure this package exists on the forge 
```

## Documentation

- [Pixi's up to date documentation about ROS integration](http://pixi.prefix.dev/latest/tutorials/ros2/)
- []
