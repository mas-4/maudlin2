from app.site import j2env
from app.models import Topic, Session, Article, Headline
import pandas as pd

class TopicsPage:
    template = j2env.get_template('topics.html')
    graph_path = 'topics_graph.png'

    def generate(self):
        with Session() as session:
            topics = session.query(Topic).all()
            for topic in topics:
                self.generate_topic_wordcloud(topic)
                session.expunge(topic)
        self.generate_graphs()
        return self.template.render(topics=topics, graph_path=self.graph_path)


    def generate_topic_wordcloud(self, topic: Topic):
        pass

    def generate_graphs(self):
        columns = {
            'afinn': Headline.afinn,
            'vader': Headline.vader_compound,
            'position': Headline.position,
            'topic_id': Article.topic_id,
            'topic': Topic.name,
            'first_accessed': Article.first_accessed,
            'last_accessed': Article.last_accessed,
        }
        with Session() as session:
            data = session.query(*list(columns.values())).all()
        df = pd.DataFrame(data, columns=list(columns.keys()))
        df['duration'] = (df['last_accessed'] - df['first_accessed']).dt.days
        df['sentiment'] = df[['afinn', 'vader']].mean(axis=1)
