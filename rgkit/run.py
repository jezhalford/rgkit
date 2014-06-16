#!/usr/bin/env python2

import argparse
from argparse import RawTextHelpFormatter
import ast
import copy
import imp
import inspect
import pkg_resources
import random
import os
import sys

try:
    imp.find_module('rgkit')
except ImportError:
    # force rgkit to appear as a module when run from current directory
    from os.path import dirname, abspath
    cdir = dirname(abspath(inspect.getfile(inspect.currentframe())))
    parentdir = dirname(cdir)
    sys.path.insert(0, parentdir)

from rgkit.settings import settings as default_settings
from rgkit import game
from rgkit.game import Player


class Options:
    def __init__(self, map_filepath=None, print_info=False,
                 animate_render=False, play_in_thread=False, curses=False,
                 game_seed=None, match_seeds=None, quiet=0, symmetric=True,
                 n_of_games=1, start=0):

        if map_filepath is None:
            map_filepath = os.path.join(os.path.dirname(__file__),
                                        'maps/default.py')
        self.animate_render = animate_render
        self.curses = curses
        self.game_seed = game_seed
        self.map_filepath = map_filepath
        self.match_seeds = match_seeds
        self.n_of_games = n_of_games
        self.play_in_thread = play_in_thread
        self.print_info = print_info
        self.quiet = quiet
        self.start = start
        self.symmetric = symmetric

    def __eq__(self, other):
        return (self.animate_render == other.animate_render and
                self.curses == other.curses and
                self.game_seed == other.game_seed and
                self.map_filepath == other.map_filepath and
                self.match_seeds == other.match_seeds and
                self.n_of_games == other.n_of_games and
                self.play_in_thread == other.play_in_thread and
                self.print_info == other.print_info and
                self.quiet == other.quiet and
                self.start == other.start and
                self.symmetric == other.symmetric)


class Runner:
    def __init__(self, players=None, player_files=None, settings=None,
                 options=None, delta_callback=None):

        if settings is None:
            settings = Runner.default_settings()
        if options is None:
            options = Options()
        if players is None:
            players = []

        self._map_data = ast.literal_eval(open(options.map_filepath).read())
        self.settings = settings
        self.settings.init_map(self._map_data)
        # Players can only be initialized from file after initializing settings
        if player_files is not None:
            for player_file in player_files:
                players.append(self._make_player(player_file))
        self._players = players
        self._delta_callback = delta_callback
        self._names = []
        for player in players:
            self._names.append(player.name())
        self.options = options

        if Runner.is_multiprocessing_supported():
            import multiprocessing
            self._rgcurses_lock = multiprocessing.Lock()
        else:
            self._rgcurses_lock = None

    @staticmethod
    def from_robots(robots, settings=None, options=None,
                    delta_callback=None):

        players = []
        for robot in robots:
            players.append(Player(robot=robot))

        return Runner(players,
                      settings=settings, options=options,
                      delta_callback=delta_callback)

    @staticmethod
    def from_command_line_args(args):
        map_name = os.path.join(args.map)

        options = Options(animate_render=args.animate,
                          curses=args.curses,
                          game_seed=args.game_seed,
                          map_filepath=map_name,
                          match_seeds=args.match_seeds,
                          n_of_games=args.count,
                          play_in_thread=args.play_in_thread,
                          print_info=not args.headless,
                          quiet=args.quiet,
                          start=args.start,
                          symmetric=not args.random)
        # TODO: generalize to N player files
        player_files = [args.player1, args.player2]
        return Runner(player_files=player_files, options=options)

    @staticmethod
    def _make_player(file_name):
        try:
            return game.Player(file_name=file_name)
        except IOError, msg:
            if pkg_resources.resource_exists('rgkit', file_name):
                bot_filename = pkg_resources.resource_filename('rgkit',
                                                               file_name)
                return game.Player(file_name=bot_filename)
            raise IOError(msg)

    @staticmethod
    def default_map():
        map_path = os.path.join(os.path.dirname(__file__), 'maps/default.py')
        return map_path

    @staticmethod
    def default_settings():
        return default_settings

    def game(self, record_turns=False, unit_testing=False):
        return game.Game(self._players, record_turns=record_turns,
                         unit_testing=unit_testing)

    def run(self):
        scores = []
        printed = []
        for i in xrange(self.options.start,
                        self.options.start + self.options.n_of_games):
            # A sequential, deterministic seed is used for each match that can
            # be overridden by user provided ones.
            match_seed = str(self.options.game_seed) + '-' + str(i)
            if self.options.match_seeds and i < len(self.options.match_seeds):
                match_seed = self.options.match_seeds[i]
            result = self.play(match_seed)
            scores.append(result)
            printed.append('{0} - seed: {1}'.format(result, match_seed))
        if args.quiet < 4:
            unmute_all()
            print '\n'.join(printed)
        return scores

    def play(self, match_seed):
        if self.options.play_in_thread:
            g = game.ThreadedGame(self._players,
                                  print_info=self.options.print_info,
                                  record_actions=self.options.print_info,
                                  record_history=True,
                                  seed=match_seed,
                                  quiet=self.options.quiet,
                                  delta_callback=self._delta_callback,
                                  symmetric=self.options.symmetric)
        else:
            g = game.Game(self._players,
                          print_info=self.options.print_info,
                          record_actions=self.options.print_info,
                          record_history=True,
                          seed=match_seed,
                          quiet=self.options.quiet,
                          delta_callback=self._delta_callback,
                          symmetric=self.options.symmetric)

        if self.options.print_info and not self.options.curses:
            # only import render if we need to render the game;
            # this way, people who don't have tkinter can still
            # run headless
            from rgkit.render import render

        g.run_all_turns()

        if self.options.print_info and not self.options.curses:
            # print "rendering %s animations" % ("with"
            #                                    if animate_render
            #                                    else "without")
            render.Render(g, self.options.animate_render, names=self._names)

        # TODO: Displaying multiple games using curses is still a little bit
        # buggy but at least it doesn't completely screw up the state of the
        # terminal anymore.  The plan is to show each game sequentially.
        # Concurrency in run.py needs some more work before the bugs can be
        # fixed. Need to make sure nothing is printing when curses is running.
        if self.options.print_info and self.options.curses:
            from rgkit import rgcurses
            rgc = rgcurses.RGCurses(g, self._names)
            if self._rgcurses_lock:
                self._rgcurses_lock.acquire()
            rgc.run()
            if self._rgcurses_lock:
                self._rgcurses_lock.release()

        return g.get_scores()

    @staticmethod
    def is_multiprocessing_supported():
        is_multiprocessing_supported = True
        try:
            imp.find_module('multiprocessing')
        except ImportError:
            # the OS does not support it. See http://bugs.python.org/issue3770
            is_multiprocessing_supported = False

        return is_multiprocessing_supported


def _task(arg):
    return Runner.from_command_line_args(arg).run()


def run_concurrently(args):
    import multiprocessing
    num_cpu = multiprocessing.cpu_count()
    (games_per_cpu, remainder) = divmod(args.count, num_cpu)
    data = []
    start = 0
    for i in xrange(num_cpu):
        copy_args = copy.deepcopy(args)

        if i == 0:
            copy_args.count = games_per_cpu + remainder
            start += games_per_cpu + remainder
        else:
            copy_args.count = games_per_cpu
            copy_args.start = start
            start += games_per_cpu

        data.append(copy_args)

    pool = multiprocessing.Pool(num_cpu)
    results = pool.map(_task, data)
    return [score for scores in results for score in scores]


def get_arg_parser():
    parser = argparse.ArgumentParser(
        description="Robot game execution script.",
        formatter_class=RawTextHelpFormatter)
    parser.add_argument("player1",
                        help="File containing first robot class definition.")
    parser.add_argument("player2",
                        help="File containing second robot class definition.")
    default_map = pkg_resources.resource_filename('rgkit', 'maps/default.py')
    parser.add_argument("-m", "--map",
                        help="User-specified map file.",
                        default=default_map)
    parser.add_argument("-c", "--count", type=int,
                        default=1,
                        help="Game count, default: 1, multithreading if >1")
    parser.add_argument("-A", "--animate", action="store_true",
                        default=False,
                        help="Enable animations in rendering.")
    parser.add_argument(
        "-q", "--quiet", action="count", help="""Quiet execution.
-q : suppresses bot stdout
-qq: suppresses bot stdout and stderr
-qqq: supresses all rgkit and bot output
-qqqq: final summary only""")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-H", "--headless", action="store_true",
                       default=False,
                       help="Disable rendering game output.")
    group.add_argument("-T", "--play-in-thread", action="store_true",
                       default=False,
                       help="Separate GUI thread from robot move calculations."
                       )
    group.add_argument("-C", "--curses", action="store_true",
                       default=False,
                       help="Display game in command line using curses.")
    parser.add_argument("--game-seed",
                        default=random.randint(0, default_settings.max_seed),
                        help="Appended with game countfor per-match seeds.")
    parser.add_argument(
        "--match-seeds", nargs='*',
        help="Used for random seed of the first matches in order.")
    parser.add_argument("-r", "--random", action="store_true",
                        default=False,
                        help="Bots spawn randomly instead of symmetrically.")
    parser.add_argument("-M", "--heatmap", action="store_true",
                        default=False,
                        help="Print heatmap after playing a number of games.")
    parser.add_argument("-s", "--start", type=int, default=0,
                        help="Starting index of matches, useful for resuming.")

    return parser


def mute_all():
    sys.stdout = game.NullDevice()
    #sys.stderr = game.NullDevice()


def unmute_all():
    sys.stdout = sys.__stdout__
    #sys.stderr = sys.__stderr__


def print_score_grid(scores, player1, player2, size):
    max_score = 50

    def to_grid(n):
        return int(round(float(n) / max_score * (size - 1)))

    def print_heat(n):
        if n > 9:
            sys.stdout.write(" +")
        else:
            sys.stdout.write(" " + str(n))

    grid = [[0 for c in xrange(size)] for r in xrange(size)]

    for s1, s2 in scores:
        grid[to_grid(s1)][to_grid(s2)] += 1

    p1won = sum(p1 > p2 for p1, p2 in scores)
    str1 = player1 + " : " + str(p1won)
    if len(str1) + 2 <= 2 * size - len(str1):
        str1 = " " + str1 + " "
        print "*" + str1 + "-" * (2 * size - len(str1)) + "*"
    else:
        print str1
        print "*" + "-" * (2 * size) + "*"

    for r in xrange(size - 1, -1, -1):
        sys.stdout.write("|")
        for c in xrange(size):
            if grid[r][c] == 0:
                if r == c:
                    sys.stdout.write(". ")
                else:
                    sys.stdout.write("  ")
            else:
                print_heat(grid[r][c])
        sys.stdout.write("|\n")

    p2won = sum(p2 > p1 for p1, p2 in scores)
    str2 = player2 + " : " + str(p2won)
    if len(str2) + 2 <= 2 * size - len(str2):
        str2 = " " + str2 + " "
        print "*" + "-" * (2 * size - len(str2)) + str2 + "*"
    else:
        print "*" + "-" * (2 * size) + "*"
        print str2


def main():
    args = get_arg_parser().parse_args()

    if args.quiet >= 3:
        mute_all()

    print('Game seed: {0}'.format(args.game_seed))
    if Runner.is_multiprocessing_supported() and args.count > 1:
        runner = run_concurrently
    else:
        runner = lambda _args: Runner.from_command_line_args(_args).run()
    scores = runner(args)

    if args.quiet >= 3:
        unmute_all()
    p1won = sum(p1 > p2 for p1, p2 in scores)
    p2won = sum(p2 > p1 for p1, p2 in scores)
    if args.heatmap:
        print_score_grid(scores, args.player1, args.player2, 26)
    print [p1won, p2won, args.count - p1won - p2won]


if __name__ == '__main__':
    main()
