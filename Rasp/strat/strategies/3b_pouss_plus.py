from strat.actions import RobotActions
import time
METADATA={"name":"3b_pouss_plus"}
def run(robot: RobotActions):
    print("Start 3b_pouss_plus")
    robot.set_pos(148, 1149, 0)
    robot.play_sound("match_loop.mp3")
    robot.goto(700, 1250, 0)
    robot.goto(900, 1250, 0)
    robot.pousse_kapla()
    robot.goto(800, 1250, 0)
    robot.goto(1200, 600, -90)
    robot.goto(1200, 300, -90)
    robot.pousse_kapla()
    robot.goto(1200, 500, -90)
    robot.goto(1800, -100, 90)
    robot.goto(1800, 500, 90)
    robot.pousse_kapla()
    robot.goto(1800, 300, 90)
    robot.goto(1500, 600, 90)
    robot.goto(1200, 1100, 180)
    robot.play_sound("outro.mp3")
    
    print("End")