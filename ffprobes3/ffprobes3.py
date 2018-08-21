import os
import pathlib
# import pipes
# import platform
import re
import shlex
import subprocess
# import math

from ffprobes3.exceptions import FFProbeError


class FFProbes3:
    """
    FFProbes3 wraps the ffprobe command and pulls the data into an object.
    For example:
    metadata = FFProbes3("this_is_a_multimedia_file.mp4')
   """

    def __init__(self, video_file):

        self.video_file = pathlib.Path(video_file)

        if video_file.is_file():

            # if str(platform.system()) == 'Windows':
            #     cmd = ["ffprobe", "-show_streams", self.video_file]
            # else:
            #     cmd = ["ffprobe -show_streams " + pipes.quote(self.video_file)]
            try:
                with open(os.devnull, 'w') as tempf:
                    subprocess.check_call(["ffprobe", "-h"], stdout=tempf, stderr=tempf)
            except IOError as e:
                raise IOError('ffprobe not found.')

            cmd = ["ffprobe -show_streams " + shlex.quote(str(self.video_file))]

            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            self.format = None
            self.created = None
            self.duration = None
            self.start = None
            self.bitrate = None
            self.streams = []
            self.video = []
            self.audio = []
            data_lines = []
            for a in iter(p.stdout.readline, b''):
                a = a.decode('UTF-8')
                if re.match(r'\[STREAM\]', a):
                    data_lines = []
                elif re.match(r'\[/STREAM\]', a):
                    self.streams.append(FFStream(data_lines))
                    data_lines = []
                else:
                    data_lines.append(a)
            for a in iter(p.stderr.readline, b''):
                a = a.decode('UTF-8')
                if re.match(r'\[STREAM\]', a):
                    data_lines = []
                elif re.match(r'\[/STREAM\]', a):
                    self.streams.append(FFStream(data_lines))
                    data_lines = []
                else:
                    data_lines.append(a)
            p.stdout.close()
            p.stderr.close()
            for a in self.streams:
                if a.is_audio():
                    self.audio.append(a)
                if a.is_video():
                    self.video.append(a)
        else:
            raise IOError('No such media file ' + str(self.video_file))


class FFStream:
    """
An object representation of an individual stream in a multimedia file.


:class:`FFStream` objects are created from :class:`FFProbes3` as it reads the file.
The constructor creates a dynamic list of attributes, based on the "xx = yy" format of
ffprobe's text output.


For example, two lines of ffprobe's output like these::

    avg_frame_rate=0/0
    time_base=1/48000

will generate these :class:`FFStream`'s attributes::

    avg_frame_rate
    time_base

with these values::

    0/0
    1/48000

:param list data_lines: list of lines from the output obtained from ffprobe
    """

    def __init__(self, data_lines):
        for a in data_lines:
            (key, val) = a.strip().split('=')
            self.__dict__[key] = val

    def is_audio(self):
        """
        Is this stream labelled as an audio stream?
        """
        val = False
        if self.__dict__['codec_type']:
            if str(self.__dict__['codec_type']) == 'audio':
                val = True
        return val

    def is_video(self):
        """
        Is the stream labelled as a video stream.
        """
        val = False
        if self.__dict__['codec_type']:
            if self.__dict__['codec_type'] == 'video':
                val = True
        return val

    def is_subtitle(self):
        """
        Is the stream labelled as a subtitle stream.
        """
        val = False
        if self.__dict__['codec_type']:
            if self.__dict__['codec_type'] == 'subtitle':
                val = True
        return val

    def frame_size(self):
        """
        Returns the pixel frame size as an integer tuple (width,height) if the stream is a video stream.
        Returns None if it is not a video stream.
        """
        size = None
        if self.is_video():
            width = self.__dict__['width']
            height = self.__dict__['height']
            if width and height:
                try:
                    size = (int(width), int(height))
                except ValueError:
                    raise FFProbeError("None integer size %s:%s" % (width, height))

        return size

    def pixel_format(self):
        """
        Returns a string representing the pixel format of the video stream. e.g. yuv420p.
        Returns none is it is not a video stream.
        """
        f = None
        if self.is_video():
            if self.__dict__['pix_fmt']:
                f = self.__dict__['pix_fmt']
        return f

    def frames(self):
        """
        Returns the length of a video stream in frames. Returns 0 if not a video stream.
        """
        frame_count = 0
        if self.is_video() or self.is_audio():
            try:
                # Easiest way: ffprobe reported it directly
                if self.__dict__['nb_frames'] != "N/A":
                    frame_count = int(self.__dict__['nb_frames'])
                # Hard way: no ffprobe info, maybe some into metadata, let's check it out
                elif self.__dict__['TAG:DURATION']:
                    match = re.search("^(?:00|(\d\d)):?(?:00|(\d\d)):?(?:00|(\d\d))\.(\d+)", self.__dict__['TAG:DURATION'])
                    if match:
                        # This is an example of the TAG:DURATION field value: 00:03:50.070000000
                        if match.group(1):
                            hours = match.group(1)
                            frame_count += int(hours) * 60 * 60
                        if match.group(2):
                            mins = match.group(2)
                            frame_count += int(mins) * 60
                        if match.group(3):
                            seconds = match.group(3)
                            frame_count += int(seconds)

                        # we know how many seconds the media lasts, let's try to find the fps and
                        # calculate the number of frames
                        # TODO: I can use the get_avg_frame_rate method too... I should detect if the fps are
                        # fixed or average someway.

                        fps = self.get_r_frame_rate()
                        frame_count = frame_count * fps

                        # TODO: This are the remaining frames, es. 070000000 in  00:03:50.070000000
                        # I don't know how to treat them: 070000000 = 7 frames?
                        # if match.group(4):
                        #     frame_count += int(match.group(4))
                else:
                    raise ValueError

            except ValueError:
                raise FFProbeError('None integer frame count')
        return frame_count

    def duration_seconds(self):
        """
        Returns the runtime duration of the video stream as a floating point number of seconds.
        Returns 0.0 if not a video stream.
        """
        duration = 0.0
        if self.is_video() or self.is_audio():
            try:
                if self.__dict__['duration'] != "N/A":
                    duration = float(self.__dict__['duration'])
                else:
                    # TODO: Hard way, may not work everytime
                    fps = self.get_avg_frame_rate()
                    framenumbers = self.frames()
                    duration = float(framenumbers / fps)
            except ValueError:
                raise FFProbeError('None numeric duration')
        return duration

    def language(self):
        """
        Returns language tag of stream. e.g. eng
        """
        lang = None
        if self.__dict__['TAG:language']:
            lang = self.__dict__['TAG:language']
        return lang

    def codec(self):
        """
        Returns a string representation of the stream codec.
        """
        codec_name = None
        if self.__dict__['codec_name']:
            codec_name = self.__dict__['codec_name']
        return codec_name

    def codec_description(self):
        """
        Returns a long representation of the stream codec.
        """
        codec_d = None
        if self.__dict__['codec_long_name']:
            codec_d = self.__dict__['codec_long_name']
        return codec_d

    def codec_tag(self):
        """
        Returns a short representative tag of the stream codec.
        """
        codec_t = None
        if self.__dict__['codec_tag_string']:
            codec_t = self.__dict__['codec_tag_string']
        return codec_t

    def bit_rate(self):
        """
        Returns bit_rate as an integer in bps
        """
        b = 0
        if self.__dict__['bit_rate']:
            try:
                b = int(self.__dict__['bit_rate'])
            except ValueError:
                raise FFProbeError('None integer bit_rate')
        return b

    def get_r_frame_rate(self):
        """
        Returns the fps value for the stream
        """

        b = float(0)

        try:
            if self.__dict__['r_frame_rate']:
                # Check for a "/" sign in the string
                match = re.search("(\d+)(?:/(\d+))?", self.__dict__['r_frame_rate'])
                if match:
                    if match.group(1):
                        # This is the numerator. es 30000
                        b = float(match.group(1))
                        if match.group(2):
                            # If present, we divide the above for this one (es. 1001)
                            # result: 29.96 or kinda.
                            b = b / float(match.group(2))
                            # just 2 decimal digits
                            b = round(b, 2)
                    else:
                        raise ValueError
                else:
                    # no "/" simbol, it should be the fps
                    b = float(self.__dict__['r_frame_rate'])

        except ValueError:
            raise FFProbeError('Nothing useful in r_frame_rate')

        return b

    def get_avg_frame_rate(self):
        """
        Returns the average fps value for the stream
        """
        try:
            if self.__dict__['avg_frame_rate']:
                match = re.search("(\d+)(?:/(\d+))?", self.__dict__['avg_frame_rate'])
                if match:
                    if match.group(1):
                        b = float(match.group(1))
                        if match.group(2):
                            b = b / float(match.group(2))
                            b = round(b, 2)
                    else:
                        raise ValueError
                else:
                    b = float(self.__dict__['avg_frame_rate'])
            else:
                raise ValueError
        except ValueError:
            raise FFProbeError('Nothing useful in r_frame_rate')

        return b
