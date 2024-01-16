from scraper.scrapers.cnn import CNNScraper


class Queue:
    def __init__(self):
        self.items = ['a', 'b', 'c']

    def run(self):
        self.items = []


def main():

    cnn = CNNScraper()
    cnn.start()
    while True:
        if cnn.done:
            break


if __name__ == '__main__':
    main()
