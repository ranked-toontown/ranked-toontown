# Ranked Toontown
Welcome to the Ranked Toontown repository! This modded Toontown client/server is the successor to
`TT-CL-Edition` (Toontown: Crane League Edition) and has a heavy focus on competitive craning, with features
such as a ranked ELO system, and standardized RNG within the crane round. The craning also **almost perfectly** emulates
the craning changes made in Corporate Clash's 1.2.8 update, which is considered to be the competitive standard
for the craning community. 

Let me reiterate, this source is designed to **emulate** Clash gameplay specifically in the crane round. We are not trying
to steal clash's ideas, gameplay, or anything of that nature. 

This source has quite the history, so I will try to break it down really quick.

This source is built off of [Toontown: Archipelago](https://github.com/toontown-archipelago/toontown-archipelago), as
it is by far the **best** publically available offline source to make modifications to. 

Toontown: Archipelago was built off of `TT-CL-Edition`, as there was lots of quality of life additions already added
such as custom keybinds, orbital camera, and most importantly, Corporate Clash's 1.2.8 craning mechanics.

`TT-CL-Edition` was built on the foundation of Toontown Offline's Toontown School House's source code.
Toontown School House is a course dedicated to teaching members of the Toontown community how to develop for the game. For more information, head over to [this](https://www.reddit.com/r/Toontown/comments/doszgg/toontown_school_house_learn_to_develop_for/) Reddit post.

This modded version of the game also contains a lot of fun additions that are meant to spice up boss round gameplay, but
there is a **heavy** focus on the crane round.

# Source Code
This source code is based on a March 2019 fork of Toontown Offline v1.0.0.0 used for Toontown School House. 
It has been stripped of all Toontown Offline exclusive features, save one. The brand new Magic Words system made for 
Toontown Offline has been left alone, and upgraded to the most recent build. This feature will allow users to easily navigate around Toontown without any hassle.

On top of that, this source code has also been updated to Python 3, utilizing a more modern version of Panda3D. 

Credits:
* **The Toontown Offline Team** for the foundation of this codebase (Toontown Schoolhouse)
* [The Corporate Clash Crew](https://corporateclash.net) for toon models, some various textures, and assistance with implementing v1.2.8 craning
* **Polygon** for making the Corporate Clash toon models
* [Open Toontown](https://github.com/open-toontown) for providing a great reference for a Toontown codebase ported to Python 3 and the HD Mickey Font
* [Astron](https://github.com/Astron/Astron)
* [Panda3D](https://github.com/panda3d/panda3d)
* [libotp-nametags](https://github.com/loblao/libotp-nametags)
* Reverse-engineered Toontown Online client/server source code is property of The Walt Disney Company.

# Getting Started

At this time, Windows is the only supported platform. For other platforms, please see [Running From Source.](#running-from-source)

### Windows

todo

### Docker (Linux Server)

Before starting, please ensure you have Docker and Docker Compose installed.
You can find out how to install them [here.](https://docs.docker.com/engine/install/)

1. Download the `Source Code (ZIP)` from [here](https://github.com/ranked-toontown/ranked-toontown/releases/latest) or clone this repository.
2. Extract the ZIP to a folder of your choice. (If you downloaded the ZIP!)
3. Using `cd`, navigate to the `launch/docker` directory.
4. Start the server using `docker compose up`. This may take a while.
5. Press `Control+C` to stop the server.
6. (Optional) If you want to utilize features such as MongoDB, you need to edit `astron/config/astrond.yml` and `launch/docker/.env`.

# Running from source

## Panda3D
This source can be run using any modern version of Panda3D. It is highly recommended that you don't install Panda3D
as it is installed automatically as a pip dependency. If you have issues launching the source, it is **more than likely**
that you have a Python PATH conflict. If this occurs, the simplest solution is to **uninstall all instances of Panda3D and Python**
on your computer, reinstall Python 3.12, and try again. **Ensure that you add Python to your PATH during install.**

## Starting the game

Please navigate to the `/launch` directory, then your platform:
- Windows: `/windows`
- Mac: `/darwin`
- Linux: `/linux`

Then run the following scripts in order:
- `/server/start_astron_server`
- `/server/start_uberdog_server`
- `/server/start_ai_server`
- `./start_game`

## Common Issues/FAQ

### I set up the server and everything is running fine. I can connect to my own server but my friends can't. Why?

If you are hosting a Mini-Server, you **must** port forward to allow incoming connections on port `7198`.
There are two ways to accomplish this:

- Port forward the port `7198` in your router's settings.
- Use a third party program (such as Hamachi) to emulate a LAN connection over the internet.

As router settings are wildly different, I cannot provide a tutorial on how to do this on this README for your specific
router. However, the process is pretty straight forward assuming you have access to your router's settings. 
You should be able to figure it out with a bit of research on Google.


### I launched the game and I am getting the error: The system cannot find the path specified

There are multiple reasons that can cause this to occur. Feel free to ask any of the contributors in the Discord for assistance.
If you want to try to resolve this issue on your own, you should **uninstall every instance of Panda3D and Python** on your system.
Once you do that, **install Python 3.12** from their official website. Ensure that when you are running through the install
wizard, that you **make sure that add Python to PATH** is checked. This is important as it is how Toontown knows how to launch.
If you are more technical savvy, ensure that your `PPYTHON_PATH` (next to the start game script) **directly matches** the `python` command that triggers
a Python3.12 environment for you.

### I logged in and I have no gags and can't go anywhere.... why can't I play?

This game is specifically designed for minigames on the Trolley, with a heavy focus on the crane round. That's it. That's the entire game.


### I was playing and my game crashed :(

Ranked Toontown is currently in an early alpha build so many issues are expected to be present. If you found a
crash/bug, feel free to [create an Issue](https://github.com/ranked-toontown/ranked-toontown/issues/new) on the GitHub page for the repository. Developers/contributors
use this as a "todo list". If you choose to do this, try and be as descriptive as possible on what caused the crash, and 
any sort of possible steps that can be taken to reproduce it.


### I was playing and the district reset :(

Similarly to a game crash, sometimes the district can crash. Follow the same steps as the previous point.